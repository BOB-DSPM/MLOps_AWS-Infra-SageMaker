import boto3
rt = boto3.client("sagemaker-runtime", region_name="ap-northeast-2")
endpoint = "my-mlops-dev-endpoint"

# XGBoost(binary:logistic) 입력: 라벨 없이 feature만 CSV (행 단위)
payload = "-0.2,0.7,-1.1,0.3,0.05\n0.1,-0.2,0.3,0.4,-0.5\n"

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
print("preds:", preds)             # [0, 0]
