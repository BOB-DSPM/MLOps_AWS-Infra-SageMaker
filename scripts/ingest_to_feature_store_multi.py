import argparse
import os
import time
import json
from datetime import datetime, timezone
import boto3
import pandas as pd
import numpy as np
import psycopg2
from sagemaker.session import Session
from sagemaker.feature_store.feature_group import FeatureGroup as SmFeatureGroup


def get_rds_connection(secret_arn: str, endpoint: str, port: int = 5432, database: str = "mlopsdb"):
    """RDS 데이터베이스 연결 생성"""
    # Secrets Manager에서 자격 증명 가져오기
    secrets_client = boto3.client('secretsmanager')
    secret_response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(secret_response['SecretString'])
    
    # PostgreSQL 연결
    conn = psycopg2.connect(
        host=endpoint,
        port=port,
        database=database,
        user=secret['username'],
        password=secret['password']
    )
    return conn


def setup_rds_tables(conn):
    """RDS에 테스트용 테이블 생성 및 샘플 데이터 삽입"""
    cursor = conn.cursor()
    
    # 테이블 존재 확인
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'ad_click_data'
        );
    """)
    table_exists = cursor.fetchone()[0]
    
    if not table_exists:
        print("Creating ad_click_data table...")
        # 테이블 생성
        cursor.execute("""
            CREATE TABLE ad_click_data (
                id SERIAL PRIMARY KEY,
                full_name VARCHAR(100),
                age INTEGER,
                gender VARCHAR(20),
                device_type VARCHAR(50),
                ad_position VARCHAR(50),
                browsing_history VARCHAR(100),
                time_of_day VARCHAR(50),
                click INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 샘플 데이터 삽입
        print("Inserting sample data...")
        sample_data = [
            ('User1001', 25, 'Male', 'Desktop', 'Top', 'Shopping', 'Morning', 1),
            ('User1002', 34, 'Female', 'Mobile', 'Side', 'Entertainment', 'Afternoon', 0),
            ('User1003', 28, 'Non-Binary', 'Desktop', 'Bottom', 'Education', 'Evening', 1),
            ('User1004', 45, 'Male', 'Mobile', 'Top', 'News', 'Night', 0),
            ('User1005', 31, 'Female', 'Desktop', 'Side', 'Social Media', 'Morning', 1),
        ]
        
        cursor.executemany("""
            INSERT INTO ad_click_data 
            (full_name, age, gender, device_type, ad_position, browsing_history, time_of_day, click)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, sample_data)
        
        conn.commit()
        print(f"Created table and inserted {len(sample_data)} sample records")
    else:
        print("Table ad_click_data already exists")
    
    cursor.close()


def read_data_from_rds(conn):
    """RDS에서 데이터 읽기"""
    print("Reading data from RDS...")
    df = pd.read_sql_query("""
        SELECT id, full_name, age, gender, device_type, ad_position, 
               browsing_history, time_of_day, click
        FROM ad_click_data
        ORDER BY id
    """, conn)
    print(f"Read {len(df)} records from RDS")
    return df


def read_data_from_s3(s3_uri: str):
    """S3에서 데이터 읽기"""
    print(f"Reading data from S3: {s3_uri}")
    df = pd.read_csv(s3_uri)
    print(f"Read {len(df)} records from S3")
    return df


def ensure_bucket_obj(s3, bucket: str, key: str, local_path: str):
    """S3에 파일 업로드 (기존 함수)"""
    try:
        s3.head_object(Bucket=bucket, Key=key)
        print(f"S3 object s3://{bucket}/{key} already exists")
    except Exception:
        print(f"Uploading {local_path} -> s3://{bucket}/{key}")
        s3.upload_file(local_path, bucket, key)
    return f"s3://{bucket}/{key}"


def ensure_feature_group(sm_client, sm_sess: Session, name: str, role_arn: str, offline_s3_uri: str, kms_key_arn: str | None):
    """Feature Group 생성 또는 기존 것 사용 (기존 함수)"""
    try:
        sm_client.describe_feature_group(FeatureGroupName=name)
        print(f"Feature Group '{name}' already exists")
        return {"created": False, "added": []}
    except Exception:
        pass

    feature_definitions = [
        {"FeatureName": "id", "FeatureType": "Integral"},
        {"FeatureName": "event_time", "FeatureType": "String"},
        {"FeatureName": "gender", "FeatureType": "Integral"},
        {"FeatureName": "age", "FeatureType": "Integral"},
        {"FeatureName": "device", "FeatureType": "Integral"},
        {"FeatureName": "hour", "FeatureType": "Integral"},
        {"FeatureName": "click", "FeatureType": "Integral"},
    ]

    offline_store_config = {"S3StorageConfig": {"S3Uri": offline_s3_uri}}
    if kms_key_arn:
        offline_store_config["S3StorageConfig"]["KmsKeyId"] = kms_key_arn

    online_store_config = {"EnableOnlineStore": True}
    if kms_key_arn:
        online_store_config["SecurityConfig"] = {"KmsKeyId": kms_key_arn}

    print(f"Creating Feature Group '{name}'...")
    sm_client.create_feature_group(
        FeatureGroupName=name,
        RecordIdentifierFeatureName="id",
        EventTimeFeatureName="event_time",
        FeatureDefinitions=feature_definitions,
        OnlineStoreConfig=online_store_config,
        OfflineStoreConfig=offline_store_config,
        RoleArn=role_arn,
    )
    time.sleep(3)
    return {"created": True, "added": ["id", "event_time", "gender", "age", "device", "hour", "click"]}


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """데이터 정규화 (기존 함수와 동일)"""
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
    device_col = col("device", "platform", "is_mobile", "device_type")
    hour_col = col("hour", "hour_of_day", "time_of_day")
    ts_col = col("timestamp", "event_time", "time")
    click_col = col("clicked", "click", "label", "target", "y", "is_click")

    # Hour from explicit column or timestamp
    if ts_col and hour_col is None:
        dt = pd.to_datetime(df[ts_col], errors="coerce")
        hour = dt.dt.hour
    elif hour_col:
        # time_of_day 문자열을 시간으로 변환
        if df[hour_col].dtype == 'object':
            time_mapping = {
                'Morning': 9, 'Afternoon': 14, 'Evening': 19, 'Night': 23,
                'morning': 9, 'afternoon': 14, 'evening': 19, 'night': 23
            }
            hour = df[hour_col].map(time_mapping).fillna(12)
        else:
            hour = pd.to_numeric(df[hour_col], errors="coerce")
    else:
        hour = 12  # 기본값
    
    if isinstance(hour, pd.Series):
        hour = hour.fillna(12).astype(int) % 24
    else:
        hour = int(hour) % 24

    # Gender normalization
    if gender_col:
        g = df[gender_col]
        if g.dtype == bool:
            g = g.astype(int)
        elif g.dtype == 'object':
            gender_mapping = {
                'Male': 1, 'Female': 0, 'Non-Binary': 2, 'male': 1, 'female': 0,
                'M': 1, 'F': 0, 'N': 2, 'm': 1, 'f': 0, 'n': 2
            }
            g = g.map(gender_mapping).fillna(0)
        else:
            g = to_int_safe(g)
    else:
        g = 0

    # Age normalization
    if age_col:
        age = to_int_safe(df[age_col])
        age = age.clip(0, 100)
    else:
        age = 30

    # Device normalization
    if device_col:
        d = df[device_col]
        if d.dtype == bool:
            d = d.astype(int)
        elif d.dtype == 'object':
            device_mapping = {
                'Desktop': 0, 'Mobile': 1, 'Tablet': 2,
                'desktop': 0, 'mobile': 1, 'tablet': 2
            }
            d = d.map(device_mapping).fillna(0)
        else:
            d = to_int_safe(d)
    else:
        d = 0

    # Click normalization
    if click_col:
        click = to_int_safe(df[click_col])
    else:
        click = 0

    return pd.DataFrame({
        "gender": g,
        "age": age,
        "device": d,
        "hour": hour,
        "click": click,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Local path to CSV with click data (optional if using RDS)")
    ap.add_argument("--use-rds", action="store_true", help="Read data from RDS instead of/in addition to CSV")
    ap.add_argument("--rds-secret-arn", help="RDS credentials secret ARN")
    ap.add_argument("--rds-endpoint", help="RDS endpoint")
    ap.add_argument("--rds-port", type=int, default=5432, help="RDS port")
    ap.add_argument("--setup-rds", action="store_true", help="Setup RDS tables with sample data")
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

    # 데이터 수집
    dfs = []
    
    # RDS에서 데이터 읽기
    if args.use_rds:
        if not args.rds_secret_arn or not args.rds_endpoint:
            raise SystemExit("--rds-secret-arn and --rds-endpoint are required when using --use-rds")
        
        conn = get_rds_connection(args.rds_secret_arn, args.rds_endpoint, args.rds_port)
        
        if args.setup_rds:
            setup_rds_tables(conn)
        
        rds_df = read_data_from_rds(conn)
        dfs.append(rds_df)
        conn.close()
    
    # S3에서 데이터 읽기 (CSV 파일이 제공된 경우)
    if args.csv:
        # 로컬 CSV를 S3에 업로드
        s3 = boto3.client("s3", region_name=region)
        s3_key = "datasets/ad_click_dataset.csv"
        s3_uri = ensure_bucket_obj(s3, args.data_bucket, s3_key, args.csv)
        
        s3_df = read_data_from_s3(s3_uri)
        dfs.append(s3_df)
    
    if not dfs:
        raise SystemExit("No data sources specified. Use --csv and/or --use-rds")
    
    # 데이터 결합
    if len(dfs) > 1:
        print("Combining data from multiple sources...")
        df = pd.concat(dfs, ignore_index=True)
        print(f"Combined data: {len(df)} total records")
    else:
        df = dfs[0]
    
    # 데이터 정규화
    df = normalize_df(df)
    df["id"] = range(1, len(df) + 1)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    df["event_time"] = now

    print("Normalized DataFrame:")
    print(df.head())
    print(f"Shape: {df.shape}")

    # Feature Store 설정
    sm = boto3.client("sagemaker", region_name=region)
    sm_sess = Session()

    offline_s3 = f"s3://{args.data_bucket}/feature-store/"
    result = ensure_feature_group(sm, sm_sess, args.feature_group_name, args.sm_exec_role_arn, offline_s3, args.kms_key_arn)

    # Feature Store에 데이터 적재
    print(f"Ingesting {len(df)} records to Feature Group '{args.feature_group_name}'...")
    fg = SmFeatureGroup(name=args.feature_group_name, sagemaker_session=sm_sess)
    
    # Conservative workers if schema was just updated/created
    workers = 1 if (result.get("created") or result.get("added")) else 4
    if workers == 1:
        time.sleep(5)
    
    fg.ingest(data_frame=df, max_workers=workers, wait=True)

    print("Data ingestion completed successfully!")
    print(f"Feature Group: {args.feature_group_name}")
    print(f"Records ingested: {len(df)}")
    print(f"Sources: {'RDS + ' if args.use_rds else ''}{'S3' if args.csv else ''}")


if __name__ == "__main__":
    main()