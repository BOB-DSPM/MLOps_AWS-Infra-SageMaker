import argparse
import os
import tempfile
import numpy as np
import pandas as pd
import boto3
from urllib.parse import urlparse
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s3", required=True)
    ap.add_argument("--csv", default="")
    ap.add_argument("--use-feature-store", default="false")
    ap.add_argument("--feature-group-name", default="")
    args = ap.parse_args()

    os.makedirs("/opt/ml/processing/train", exist_ok=True)
    os.makedirs("/opt/ml/processing/validation", exist_ok=True)

    # Resolve AWS region explicitly to avoid NoRegionError inside processing containers
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        try:
            region = boto3.session.Session().region_name
        except Exception:
            region = None
    if not region:
        raise SystemExit("AWS region not found in environment; set AWS_REGION or AWS_DEFAULT_REGION")

    session = boto3.session.Session(region_name=region)
    s3c = session.client("s3")

    df = None
    if args.use_feature_store.lower() == "true" and args.feature_group_name:
        sm = session.client("sagemaker")
        athena = session.client("athena")
        desc = sm.describe_feature_group(FeatureGroupName=args.feature_group_name)
        dc = desc.get("OfflineStoreConfig", {}).get("DataCatalogConfig") or {}
        glue_tbl = dc.get("TableName")
        glue_db = dc.get("Database")
        if not glue_tbl or not glue_db:
            raise SystemExit("Feature Group offline store is not using DataCatalog; please provide ExternalCsvUri instead.")
        q = f"SELECT cast(click as integer) as label, cast(gender as integer) as gender, cast(age as integer) as age, cast(device as integer) as device, cast(hour as integer) as hour FROM \"{glue_db}\".\"{glue_tbl}\" WHERE click is not null limit 5000"
        s3_out = os.path.join(args.s3, "athena-out/")
        s3_out = s3_out if s3_out.startswith("s3://") else args.s3
        res = athena.start_query_execution(QueryString=q, ResultConfiguration={"OutputLocation": s3_out})
        qid = res["QueryExecutionId"]
        while True:
            st = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]["Status"]["State"]
            if st in ("SUCCEEDED", "FAILED", "CANCELLED"):
                if st != "SUCCEEDED":
                    raise SystemExit(f"Athena query failed: {st}")
                break
            time.sleep(3)
        s3loc = urlparse(s3_out)
        dl = f"{qid}.csv"
        tmp = tempfile.NamedTemporaryFile(delete=False)
        s3c.download_file(s3loc.netloc, os.path.join(s3loc.path.lstrip("/"), dl), tmp.name)
        raw = pd.read_csv(tmp.name)
        df = raw
    if df is None and args.csv and args.csv.startswith("s3://"):
        u = urlparse(args.csv)
        b = u.netloc
        k = u.path.lstrip("/")
        tmp = tempfile.NamedTemporaryFile(delete=False)
        s3c.download_file(b, k, tmp.name)
        raw = pd.read_csv(tmp.name)
        cols = {c.lower(): c for c in raw.columns}
        def col(*names):
            for n in names:
                if n in cols:
                    return cols[n]
            return None
        gender = raw[col("gender", "sex", "is_male")]
        if str(gender.dtype) == "bool":
            gender = gender.astype(int)
        age = raw[col("age", "user_age")]
        device = raw[col("device", "platform", "is_mobile")]
        if str(device.dtype) == "bool":
            device = device.astype(int)
        hourcol = col("hour", "hour_of_day")
        ts = col("timestamp", "event_time", "time")
        if ts and hourcol is None:
            dt = pd.to_datetime(raw[ts], errors="coerce")
            hour = dt.dt.hour.fillna(0).astype(int)
        else:
            hour = raw[hourcol].astype(int)
        click = raw[col("clicked", "click", "label", "target", "y", "is_click")].astype(int)
        out = pd.DataFrame({"label": click, 0: gender.astype(int), 1: age.astype(int), 2: device.astype(int), 3: hour.astype(int)})
        df = out
    else:
        n = 1000
        rng = np.random.default_rng(42)
        gender = rng.integers(0, 2, size=n)
        age = rng.integers(16, 71, size=n)
        device = rng.integers(0, 2, size=n)
        hour = rng.integers(0, 24, size=n)
        night = ((hour >= 20) | (hour <= 2)).astype(int)
        logit = -3.0 + 0.8 * gender + 0.03 * age + 0.5 * device + 0.4 * night
        p = 1 / (1 + np.exp(-logit))
        y = (rng.random(n) < p).astype(int)
        X = np.column_stack([gender, age, device, hour])
        df = pd.DataFrame(np.column_stack([y, X]))
    train = df.sample(frac=0.8, random_state=42)
    val = df.drop(train.index)
    train.to_csv("/opt/ml/processing/train/data.csv", index=False, header=False)
    val.to_csv("/opt/ml/processing/validation/data.csv", index=False, header=False)


if __name__ == "__main__":
    main()
