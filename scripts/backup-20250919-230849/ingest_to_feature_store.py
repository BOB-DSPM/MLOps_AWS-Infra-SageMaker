import argparse
import os
import time
from datetime import datetime, timezone
import boto3
import pandas as pd
import numpy as np
from sagemaker.session import Session
from sagemaker.feature_store.feature_group import FeatureGroup as SmFeatureGroup


def ensure_bucket_obj(s3, bucket: str, key: str, local_path: str):
    s3.upload_file(local_path, bucket, key)
    return f"s3://{bucket}/{key}"


def ensure_feature_group(sm_client, sm_sess: Session, name: str, role_arn: str, offline_s3_uri: str, kms_key_arn: str | None):
    """Ensure Feature Group exists with required schema.
    Returns dict: {created: bool, added: [feature_names]}
    If exists, add missing features and wait until they appear in DescribeFeatureGroup.
    """
    required = [
        {"FeatureName": "id", "FeatureType": "Integral"},
        {"FeatureName": "event_time", "FeatureType": "String"},
        {"FeatureName": "gender", "FeatureType": "Integral"},
        {"FeatureName": "age", "FeatureType": "Integral"},
        {"FeatureName": "device", "FeatureType": "Integral"},
        {"FeatureName": "hour", "FeatureType": "Integral"},
        {"FeatureName": "click", "FeatureType": "Integral"},
    ]
    try:
        desc = sm_client.describe_feature_group(FeatureGroupName=name)
        existing = {f["FeatureName"] for f in desc.get("FeatureDefinitions", [])}
        additions = [f for f in required if f["FeatureName"] not in existing]
        if additions:
            sm_client.update_feature_group(FeatureGroupName=name, FeatureAdditions=additions)
            # Wait until DescribeFeatureGroup reflects new features
            want = existing.union({f["FeatureName"] for f in additions})
            for _ in range(40):  # ~60-120s max
                d = sm_client.describe_feature_group(FeatureGroupName=name)
                defs = {f["FeatureName"] for f in d.get("FeatureDefinitions", [])}
                if want.issubset(defs):
                    break
                time.sleep(3)
            return {"created": False, "added": [f["FeatureName"] for f in additions]}
        return {"created": False, "added": []}
    except sm_client.exceptions.ResourceNotFound:
        pass

    offline_cfg = {"S3StorageConfig": {"S3Uri": offline_s3_uri}, "DisableGlueTableCreation": False}
    if kms_key_arn:
        offline_cfg["S3StorageConfig"]["KmsKeyId"] = kms_key_arn

    sm_client.create_feature_group(
        FeatureGroupName=name,
        RecordIdentifierFeatureName="id",
        EventTimeFeatureName="event_time",
        FeatureDefinitions=required,
        RoleArn=role_arn,
        OnlineStoreConfig={"EnableOnlineStore": True},
        OfflineStoreConfig=offline_cfg,
    )

    # Wait for feature group to be created (polling method)
    for _ in range(60):  # 5 minutes max
        try:
            desc = sm_client.describe_feature_group(FeatureGroupName=name)
            if desc.get("FeatureGroupStatus") == "Created":
                break
        except sm_client.exceptions.ResourceNotFound:
            pass
        time.sleep(5)
    # Verify schema is present
    for _ in range(40):
        d = sm_client.describe_feature_group(FeatureGroupName=name)
        defs = {f["FeatureName"] for f in d.get("FeatureDefinitions", [])}
        need = {"id", "event_time", "gender", "age", "device", "hour", "click"}
        if need.issubset(defs):
            break
        time.sleep(3)
    return {"created": True, "added": ["id", "event_time", "gender", "age", "device", "hour", "click"]}


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    cols = {c.lower(): c for c in df.columns}
    def col(*names):
        for n in names:
            if n in cols:
                return cols[n]
        return None

    def to_int_safe(series) -> pd.Series:
        return pd.to_numeric(series, errors="coerce").fillna(0).astype(int)

    # Column detection
    gender_col = col("gender", "sex", "is_male")
    age_col = col("age", "user_age")
    device_col = col("device", "platform", "is_mobile")
    hour_col = col("hour", "hour_of_day")
    ts_col = col("timestamp", "event_time", "time")
    click_col = col("clicked", "click", "label", "target", "y", "is_click")

    # Hour from explicit column or timestamp
    if ts_col and hour_col is None:
        dt = pd.to_datetime(df[ts_col], errors="coerce")
        hour = dt.dt.hour
    elif hour_col:
        hour = pd.to_numeric(df[hour_col], errors="coerce")
    else:
        hour = 0
    if isinstance(hour, pd.Series):
        hour = hour.fillna(0).astype(int) % 24
    else:
        hour = int(hour) % 24

    # Gender normalization
    if gender_col:
        g = df[gender_col]
        if g.dtype == bool:
            g = g.astype(int)
        elif g.dtype == object:
            lower = g.astype(str).str.lower()
            mapped = lower.map({
                "male": 1, "m": 1, "man": 1, "true": 1, "1": 1, "yes": 1, "y": 1,
                "female": 0, "f": 0, "woman": 0, "false": 0, "0": 0, "no": 0, "n": 0,
            })
            g = mapped.fillna(0).astype(int)
        else:
            g = to_int_safe(g)
    else:
        g = 0

    # Age normalization
    a = to_int_safe(df[age_col]) if age_col else 0

    # Device normalization
    if device_col:
        d = df[device_col]
        if d.dtype == bool:
            d = d.astype(int)
        elif d.dtype == object:
            lower = d.astype(str).str.lower()
            mapped = lower.map({
                "mobile": 1, "android": 1, "ios": 1, "iphone": 1,
                "desktop": 0, "pc": 0, "web": 0,
            })
            d = mapped.fillna(0).astype(int)
        else:
            d = to_int_safe(d)
    else:
        d = 0

    # Click/label normalization (0/1)
    if click_col:
        c = df[click_col]
        if c.dtype == bool:
            c = c.astype(int)
        elif c.dtype == object:
            lower = c.astype(str).str.lower()
            mapped = lower.map({"yes": 1, "true": 1, "1": 1, "y": 1, "clicked": 1,
                                 "no": 0, "false": 0, "0": 0, "n": 0})
            c = mapped.fillna(0).astype(int)
        else:
            c = to_int_safe(c)
    else:
        c = 0

    out = pd.DataFrame({
        "gender": g if not np.isscalar(g) else pd.Series([g] * len(df)),
        "age": a if not np.isscalar(a) else pd.Series([a] * len(df)),
        "device": d if not np.isscalar(d) else pd.Series([d] * len(df)),
        "hour": hour if not np.isscalar(hour) else pd.Series([hour] * len(df)),
        "click": c if not np.isscalar(c) else pd.Series([c] * len(df)),
    })
    out = out.fillna(0).astype(int)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Local path to CSV with click data")
    ap.add_argument("--feature-group-name", default=os.environ.get("FEATURE_GROUP_NAME", "ad-click-feature-group"))
    ap.add_argument("--data-bucket", default=os.environ.get("DATA_BUCKET"), help="S3 data bucket name")
    ap.add_argument("--sm-exec-role-arn", default=os.environ.get("SM_EXEC_ROLE_ARN"), help="SageMaker execution role ARN")
    ap.add_argument("--kms-key-arn", default=os.environ.get("KMS_KEY_ARN"), help="KMS key ARN (optional)")
    args = ap.parse_args()

    region = os.environ.get("AWS_REGION") or boto3.Session().region_name or "ap-northeast-2"
    if not args.data_bucket:
        raise SystemExit("--data-bucket or DATA_BUCKET env is required")
    if not args.sm_exec_role_arn:
        raise SystemExit("--sm-exec-role-arn or SM_EXEC_ROLE_ARN env is required")
    data_bucket = args.data_bucket
    role_arn = args.sm_exec_role_arn
    kms_arn = args.kms_key_arn

    s3 = boto3.client("s3", region_name=region)
    sm = boto3.client("sagemaker", region_name=region)
    # Session() picks up region from environment/boto config
    sm_sess = Session()

    df = pd.read_csv(args.csv)
    df = normalize_df(df)
    df["id"] = range(1, len(df) + 1)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    df["event_time"] = now

    s3_key = "datasets/ad_click_dataset.csv"
    s3_uri = ensure_bucket_obj(s3, data_bucket, s3_key, args.csv)

    offline_s3 = f"s3://{data_bucket}/feature-store/"
    result = ensure_feature_group(sm, sm_sess, args.feature_group_name, role_arn, offline_s3, kms_arn)

    fg = SmFeatureGroup(name=args.feature_group_name, sagemaker_session=sm_sess)
    # If schema was just updated/created, use conservative workers and brief delay
    workers = 1 if (result.get("created") or result.get("added")) else 4
    if workers == 1:
        time.sleep(5)
    fg.ingest(data_frame=df, max_workers=workers, wait=True)

    # After first ingestion, Glue Data Catalog table is typically created; wait up to ~60s
    glue_db = None
    glue_tbl = None
    try:
        desc = sm.describe_feature_group(FeatureGroupName=args.feature_group_name)
        dc = (desc.get("OfflineStoreConfig", {}) or {}).get("DataCatalogConfig", {}) or {}
        glue_db = dc.get("Database") or "sagemaker_featurestore"
        glue_tbl = dc.get("TableName") or args.feature_group_name
        glue = boto3.client("glue", region_name=region)
        for _ in range(12):
            try:
                glue.get_table(DatabaseName=glue_db, Name=glue_tbl)
                break
            except glue.exceptions.EntityNotFoundException:
                time.sleep(5)
    except Exception:
        pass

    print({
        "uploaded_csv": s3_uri,
        "feature_group": args.feature_group_name,
        "records": len(df),
        "glue_database": glue_db,
        "glue_table": glue_tbl,
    })


if __name__ == "__main__":
    main()
