import boto3
import datetime
rt = boto3.client("sagemaker-runtime", region_name="ap-northeast-2")
endpoint = "my-mlops-dev-endpoint"

# XGBoost(binary:logistic) 입력: 라벨 없이 feature만 CSV (행 단위)
# 본 예제의 feature 순서: gender(0/1), age(int), device(0:web,1:mobile), hour(0-23)
payload = "1,32,1,21\n0,48,0,9\n"

res = rt.invoke_endpoint(
    EndpointName=endpoint,
    ContentType="text/csv",
    Accept="text/csv",
    Body=payload,
)

raw = res["Body"].read().decode("utf-8").strip()
print("raw:", raw)                 # 예: "0.34\n0.42"
scores = [float(x) for x in raw.splitlines()]
print("scores:", scores)           # [0.34, 0.42]
preds = [int(s >= 0.5) for s in scores]
print("Test run date:", datetime.datetime.now().isoformat())
print("preds:", preds)             # [0, 0]
