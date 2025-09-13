# ─────────────────────────────────────────────────────────────────────────────
# CDK 모놀리식 예시(모듈화): "기본 리소스" VPC/S3/KMS/ECR/IAM/CodeCommit/CodeBuild/CodePipeline
# - 언어: Python (CDK v2)
# - 기본 리전: ap-northeast-2
# - 기본 프로젝트명: my-mlops
# - 목적: IaC로 고정 인프라 스캐폴드(네트워크/아티팩트/레지스트리/CI 파이프라인)를 모듈화
# - 사용법(로컬):
#   변수) export AWS_REGION=ap-northeast-2
#       export AWS_DEFAULT_REGION=ap-northeast-2
#       unset CDK_DEFAULT_REGION 
#   0) python -m venv .venv && source .venv/bin/activate
#      pip install -r requirements.txt
#   0-1) find . -type d -name "__pycache__" -exec rm -rf {} +
#   0-2) cdk synth
#   1) cdk bootstrap aws://<ACCOUNT_ID>/ap-northeast-2
#   2) cdk deploy BaseStack
#   3) (옵션) 컨텍스트 오버라이드: cdk deploy -c project_name=my-mlops -c env_name=dev -c include_vpc=true
# - 기본 생성물:
#   VPC(옵션), KMS(Key for S3), S3(artifacts/logs/data, SSL-Only+버저닝), ECR(스캔+수명정책),
#   IAM(최소권한 빌드/파이프라인 롤), CodeCommit, CodeBuild(Project), CodePipeline(소스→빌드)
# - 주의: 과금 발생 리소스 있음. 학습/개발 후 cdk destroy 권장.
# ─────────────────────────────────────────────────────────────────────────────
