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
        print(f"Using Feature Store with Feature Group: {args.feature_group_name}")
        sm = session.client("sagemaker")
        
        # Feature Store에서 온라인 스토어를 통해 데이터 샘플링
        try:
            # 온라인 스토어에서 데이터 가져오기 (실제 프로덕션에서는 더 정교한 방법 사용)
            print("Attempting to use online store for data extraction...")
            
            # 임시: 온라인 스토어 대신 S3에서 직접 읽기
            # Feature Store의 오프라인 스토어 S3 경로 확인
            desc = sm.describe_feature_group(FeatureGroupName=args.feature_group_name)
            offline_config = desc.get("OfflineStoreConfig", {})
            s3_config = offline_config.get("S3StorageConfig", {})
            resolved_s3_uri = s3_config.get("ResolvedOutputS3Uri", "")
            
            if resolved_s3_uri:
                print(f"Feature Store S3 path: {resolved_s3_uri}")
                # S3에서 파케트 파일들 목록 가져오기
                s3_uri_parts = resolved_s3_uri.replace("s3://", "").split("/", 1)
                bucket = s3_uri_parts[0]
                prefix = s3_uri_parts[1] if len(s3_uri_parts) > 1 else ""
                
                # S3에서 파케트 파일 찾기
                s3_paginator = s3c.get_paginator('list_objects_v2')
                parquet_files = []
                for page in s3_paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for obj in page.get('Contents', []):
                        if obj['Key'].endswith('.parquet'):
                            parquet_files.append(obj['Key'])
                            if len(parquet_files) >= 5:  # 최대 5개 파일만 처리
                                break
                    if len(parquet_files) >= 5:
                        break
                
                if parquet_files:
                    print(f"Found {len(parquet_files)} parquet files, using first one for sampling")
                    # 첫 번째 파케트 파일 다운로드
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.parquet')
                    s3c.download_file(bucket, parquet_files[0], tmp.name)
                    
                    # 파케트 파일 읽기
                    import pandas as pd
                    raw = pd.read_parquet(tmp.name)
                    print(f"Loaded {len(raw)} records from Feature Store")
                    
                    # 필요한 컬럼 추출 및 변환
                    df = pd.DataFrame({
                        "label": raw["click"].astype(int),
                        0: raw["gender"].astype(int),
                        1: raw["age"].astype(int), 
                        2: raw["device"].astype(int),
                        3: raw["hour"].astype(int)
                    })
                    print(f"Processed {len(df)} records for training")
                else:
                    print("No parquet files found in Feature Store, falling back to CSV")
                    raise FileNotFoundError("No data files found")
            else:
                print("No resolved S3 URI found for Feature Store")
                raise ValueError("Feature Store not properly configured")
                
        except Exception as e:
            print(f"Feature Store access failed: {e}")
            print("Falling back to CSV file approach...")
            # Feature Store 실패 시 CSV 파일로 fallback
            if args.csv and args.csv.startswith("s3://"):
                print(f"Using fallback CSV: {args.csv}")
            else:
                print("No CSV fallback available, using synthetic data")
    
    # CSV 처리 로직은 그대로 유지
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
