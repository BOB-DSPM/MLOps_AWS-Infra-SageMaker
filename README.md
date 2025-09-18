# MLOps on AWS (SageMaker + CodePipeline)

## 준비
1) 해당 레포 클론
2) 의존성 설치
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3) CDK 부트스트랩 설치 (최초 1회)
    ```bash
    cdk bootstrap aws://$AWS_ACCOUNT_ID/$AWS_REGION
    ```
## 배포
```bash
cdk deploy
```

## 파이프라인
* 소스 커밋 → Train & Register(CodeBuild) → Manual Approve → Deploy(CodeBuild)

* 학습 출력은 Model Package Group 버전으로 등록(PendingManualApproval).

* 승인 후 최신 Approved 버전이 엔드포인트에 배포/업데이트.

## SageMaker Pipelines (옵션)
CodeBuild의 Train 단계에서 SageMaker Pipeline을 실행하도록 전환할 수 있습니다.

- 설정: `cdk.json`의 context에 `"use_sm_pipeline": true` 추가
- 파이프라인 정의: `pipelines/pipeline_def.py`
    - 단계: extract → validate → preprocess → train → evaluate → (AUC 임계 통과 시) register
    - 실행: CodeBuild가 자동으로 upsert+start(wait) 수행

로컬/Studio에서 수동 실행도 가능합니다.

1) Studio/노트북에서 환경변수 설정(SM_EXEC_ROLE_ARN, DATA_BUCKET 등)
2) 파이썬 실행: `python pipelines/pipeline_def.py --run --wait`

## 기존 리소스 재사용/중복 방지
- S3 버킷(ECR)은 이미 존재하면 자동으로 참조합니다.
- Feature Group
    - 새로 생성: 기본값(`enable_feature_group` 생략 또는 true)
    - 기존 사용: `use_existing_feature_group=true`와 `feature_group_name` 지정
    - 완전 비활성화: `enable_feature_group=false`
- Studio
    - `enable_studio`로 생성/미생성 제어(기존 도메인을 그대로 사용하려면 false)

## 데이터셋 업로드 및 Feature Store 적재
CSV를 S3와 Feature Store에 적재하려면 다음을 실행하세요.

1) 환경변수 설정
    - DATA_BUCKET: 스택 Output의 DataBucket
    - SM_EXEC_ROLE_ARN: 스택에서 생성된 SageMaker 실행 역할 ARN
    - (선택) KMS_KEY_ARN, FEATURE_GROUP_NAME

2) 적재 실행
```bash
python scripts/ingest_to_feature_store.py --csv /path/to/ad_click_dataset.csv
```

실행 결과:
- S3: s3://<DataBucket>/datasets/ad_click_dataset.csv 업로드
- Feature Store: FEATURE_GROUP_NAME(기본 ad-click-feature-group) 생성/재사용 후 레코드 적재

CodeBuild(Train 단계)는 기본적으로 `s3://<DataBucket>/datasets/ad_click_dataset.csv`를 사용하도록 설정되어 있습니다(`EXTERNAL_CSV_URI`).

## 완전 재배포 가이드 (Nuke & Redeploy)

### 1. 기존 스택 완전 삭제 (Nuke)
모든 리소스를 완전히 삭제하고 처음부터 다시 배포할 때 사용합니다.

```bash
# 모든 스택 삭제 (순서 중요: 의존성 역순으로 삭제)
cdk destroy My-mlops-InferenceStack --force
cdk destroy My-mlops-DevMLOpsStack --force
cdk destroy My-mlops-DevVpcStack --force
cdk destroy My-mlops-BaseStack --force

# S3 버킷 수동 정리 (버킷이 비어있지 않으면 자동 삭제 안됨)
aws s3 rm s3://your-data-bucket-name --recursive
aws s3 rb s3://your-data-bucket-name

# ECR 레포지토리 수동 정리 (이미지가 있으면 자동 삭제 안됨)
aws ecr delete-repository --repository-name your-ecr-repo-name --force
```

### 2. 완전 재배포
```bash
# 환경 변수 설정
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=ap-northeast-2

# CDK 부트스트랩 (필요시 - 계정당 1회만)
cdk bootstrap aws://$AWS_ACCOUNT_ID/$AWS_REGION

# 전체 스택 배포 (의존성 순서대로)
cdk deploy --all --require-approval never
```

### 3. 데이터 적재 및 파이프라인 실행

#### Step 1: 환경 변수 설정
배포 완료 후 스택 Output에서 필요한 값들을 가져와 환경변수로 설정합니다.

```bash
# 스택 Output 확인
aws cloudformation describe-stacks --stack-name My-mlops-BaseStack --query 'Stacks[0].Outputs'

# 환경변수 설정 (Output에서 가져온 값으로 설정)
export DATA_BUCKET="<DataBucket-Output-Value>"
export SM_EXEC_ROLE_ARN="<SageMakerExecutionRole-Output-Value>"
export FEATURE_GROUP_NAME="ad-click-feature-group"
export KMS_KEY_ARN="<KMSKey-Output-Value>"  # 선택사항

# 예시:
# export DATA_BUCKET="my-mlops-basestack-databucket12345678-abcdefghijkl"
# export SM_EXEC_ROLE_ARN="arn:aws:iam::123456789012:role/My-mlops-BaseStack-SageMakerExecutionRole-ABCDEFGHIJKL"
```

#### Step 2: 데이터셋 업로드 및 Feature Store 적재
```bash
# CSV 파일을 S3와 Feature Store에 적재
python scripts/ingest_to_feature_store.py --csv ad_click_dataset.csv

# 실행 결과 확인
# - S3: s3://<DataBucket>/datasets/ad_click_dataset.csv 업로드 완료
# - Feature Store: ad-click-feature-group 생성 및 레코드 적재 완료
```

#### Step 3: ML 파이프라인 트리거
```bash
# CodeCommit에 더미 커밋으로 파이프라인 트리거
git add .
git commit -m "Trigger ML pipeline after redeploy"
git push origin main

# 파이프라인 실행 상태 확인
aws codepipeline get-pipeline-state --name My-mlops-BaseStack-MLOpsPipeline
```

#### Step 4: 모델 승인 및 배포
```bash
# 파이프라인의 Manual Approval 단계에서 승인 대기 상태 확인
aws codepipeline get-pipeline-execution --pipeline-name My-mlops-BaseStack-MLOpsPipeline --pipeline-execution-id <execution-id>

# 콘솔에서 수동 승인 또는 CLI로 승인
aws codepipeline put-approval-result \
  --pipeline-name My-mlops-BaseStack-MLOpsPipeline \
  --stage-name ApprovalStage \
  --action-name ManualApproval \
  --result summary="Approved for deployment",status=Approved \
  --token <approval-token>
```

### 4. 배포 검증
```bash
# 엔드포인트 상태 확인
aws sagemaker describe-endpoint --endpoint-name ad-click-prediction-endpoint

# 추론 테스트
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name ad-click-prediction-endpoint \
  --content-type text/csv \
  --body "25,1,0,1,0,0,1,1" \
  output.json && cat output.json

# Feature Store 확인
aws sagemaker describe-feature-group --feature-group-name ad-click-feature-group
```

### 주의사항
- **순서 준수**: 삭제는 의존성 역순으로, 배포는 의존성 순서대로 진행
- **S3/ECR 수동 정리**: 내용이 있는 버킷/레포지토리는 수동으로 정리 필요
- **환경변수 확인**: 각 단계에서 올바른 값이 설정되었는지 반드시 확인
- **승인 프로세스**: Manual Approval 단계에서 반드시 수동 승인 필요

<!-- Test commit to trigger pipeline -->

