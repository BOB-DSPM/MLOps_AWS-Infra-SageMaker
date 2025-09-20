# AWS Nuke 후 MLOps 인프라 재배포 완전 가이드

## 📋 사전 준비사항

### 1. 데이터 백업 체크리스트 (Nuke 실행 전 필수!)
- [ ] **Feature Store 데이터 백업**:
  ```bash
  # ad-click-dataset.csv 파일 확인 (이미 로컬에 보관됨)
  ls -la ad_click_dataset.csv
  
  # Feature Store 데이터 S3 백업 확인
  aws s3 ls s3://sagemaker-ap-northeast-2-651706765732/my-mlops-dev-feature-group-v2/ --recursive
  ```

- [ ] **Git 저장소 최신 상태 확인**:
  ```bash
  git status
  git push origin main
  git push dev main
  ```

- [ ] **현재 구성 정보 백업**:
  ```bash
  # CDK 구성 확인
  cdk list
  
  # 현재 스택 정보 백업
  aws cloudformation list-stacks --region ap-northeast-2 > backup-stacks.json
  
  # Feature Groups 정보 백업
  aws sagemaker list-feature-groups --region ap-northeast-2 > backup-feature-groups.json
  ```

### 2. Nuke 설정 파일 확인
```yaml
# aws-nuke-config.yml 예시
regions:
- ap-northeast-2

account-blocklist:
- "999999999999" # 실제 계정 번호가 아닌 것을 확인

accounts:
  "651706765732": # 실제 계정 번호
    filters:
      IAMRole:
      - "AWSServiceRole*"
      - "aws-service-role/*"
      IAMRolePolicy:
      - "AWSServiceRole*"
```

## 🚀 AWS Nuke 후 재배포 절차

### Step 1: 기본 환경 설정
```bash
# 1. Python 환경 설정
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. AWS CLI 설정 확인
aws configure list
aws sts get-caller-identity

# 3. CDK Bootstrap (Nuke 후 필수!)
cdk bootstrap aws://651706765732/ap-northeast-2
```

### Step 2: 순차적 스택 배포
```bash
# 1. Base 스택 먼저 배포
cdk deploy My-mlops-BaseStack --require-approval never

# 2. VPC 스택 배포 (네트워크 기반 먼저)
cdk deploy My-mlops-DevVpcStack --require-approval never

# 3. MLOps 스택 배포 (VPC 의존성)
cdk deploy My-mlops-DevMLOpsStack --require-approval never

# 4. Inference 스택 배포 (선택사항)
cdk deploy My-mlops-InferenceStack --require-approval never
```

### Step 3: Feature Store 재생성 및 데이터 로드
```bash
# 1. Feature Store 생성 스크립트 실행
python scripts/ingest_to_feature_store.py

# 2. Feature Store 상태 확인
aws sagemaker describe-feature-group \
  --feature-group-name ad-click-feature-group-dev \
  --region ap-northeast-2

# 3. 데이터 로드 확인
aws sagemaker search \
  --resource feature-groups \
  --search-expression '{
    "Filters": [
      {
        "Name": "FeatureGroupName",
        "Operator": "Equals",
        "Value": "ad-click-feature-group-dev"
      }
    ]
  }' \
  --region ap-northeast-2
```

### Step 4: CodeCommit 저장소 재연결
```bash
# 1. 기존 원격 저장소 제거
git remote remove aws
git remote remove dev

# 2. 새로운 CodeCommit 저장소 추가
git remote add aws https://git-codecommit.ap-northeast-2.amazonaws.com/v1/repos/my-mlops-repo
git remote add dev https://git-codecommit.ap-northeast-2.amazonaws.com/v1/repos/my-mlops-repo-dev

# 3. 첫 푸시 (새 저장소이므로)
git push aws main
git push dev main
```

### Step 5: 파이프라인 테스트
```bash
# 1. 파이프라인 생성 확인
aws sagemaker list-pipelines --region ap-northeast-2

# 2. 첫 파이프라인 실행 트리거 (CodeCommit 푸시로)
echo "# Pipeline test" >> README.md
git add README.md
git commit -m "Trigger first pipeline after AWS Nuke recovery"
git push dev main

# 3. 파이프라인 실행 상태 모니터링
aws sagemaker list-pipeline-executions \
  --pipeline-name my-mlops-repo-dev-pipeline \
  --region ap-northeast-2
```

## 🔍 재배포 후 검증 체크리스트

### 인프라 검증
- [ ] **CDK 스택 상태**:
  ```bash
  cdk list
  aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --region ap-northeast-2
  ```

- [ ] **VPC 엔드포인트 확인**:
  ```bash
  aws ec2 describe-vpc-endpoints --region ap-northeast-2 --query 'VpcEndpoints[].ServiceName'
  ```

- [ ] **IAM 역할 확인**:
  ```bash
  aws iam list-roles --query 'Roles[?contains(RoleName, `mlops`)].RoleName'
  ```

### Feature Store 검증
- [ ] **Feature Group 존재 확인**:
  ```bash
  aws sagemaker list-feature-groups --region ap-northeast-2
  ```

- [ ] **데이터 레코드 수 확인**:
  ```bash
  # Athena 쿼리로 레코드 수 확인
  aws athena start-query-execution \
    --query-string "SELECT COUNT(*) FROM \"sagemaker_featurestore\".\"ad_click_feature_group_dev_1726707669\"" \
    --result-configuration OutputLocation=s3://YOUR-QUERY-RESULTS-BUCKET/ \
    --region ap-northeast-2
  ```

### 파이프라인 검증
- [ ] **SageMaker 파이프라인 실행**:
  ```bash
  aws sagemaker start-pipeline-execution \
    --pipeline-name my-mlops-repo-dev-pipeline \
    --region ap-northeast-2
  ```

- [ ] **모든 스텝 성공 확인**:
  ```bash
  # 최신 실행 상태 확인
  EXECUTION_ARN=$(aws sagemaker list-pipeline-executions \
    --pipeline-name my-mlops-repo-dev-pipeline \
    --region ap-northeast-2 \
    --query 'PipelineExecutionSummaries[0].PipelineExecutionArn' \
    --output text)
    
  aws sagemaker list-pipeline-execution-steps \
    --pipeline-execution-arn $EXECUTION_ARN \
    --region ap-northeast-2
  ```

### 크로스 레포지토리 배포 검증
- [ ] **CodeBuild 프로젝트 확인**:
  ```bash
  aws codebuild list-projects --region ap-northeast-2 | grep cross-repo
  ```

- [ ] **크로스 레포 배포 테스트**:
  ```bash
  # 운영 레포지토리에 커밋이 자동으로 생성되는지 확인
  aws codecommit get-repository --repository-name my-mlops-repo --region ap-northeast-2
  ```

## ⚠️ 주의사항 및 트러블슈팅

### 1. Bootstrap 관련 이슈
**문제**: CDK bootstrap이 없어서 배포 실패
**해결**: 
```bash
cdk bootstrap aws://651706765732/ap-northeast-2
```

### 2. Feature Store 데이터 로드 실패
**문제**: CSV 파일을 찾지 못함
**해결**:
```bash
# CSV 파일 위치 확인
ls -la ad_click_dataset.csv
# 필요시 다시 다운로드
wget https://your-data-source/ad_click_dataset.csv
```

### 3. VPC 엔드포인트 연결 문제
**문제**: SageMaker가 외부 서비스에 접근 못함
**해결**: VPC 엔드포인트 재배포 확인
```bash
aws ec2 describe-vpc-endpoints --region ap-northeast-2 \
  --filters Name=state,Values=available
```

### 4. CodeCommit 인증 문제
**문제**: git push 실패
**해결**:
```bash
# credential helper 재설정
git config --global credential.helper '!aws codecommit credential-helper $@'
git config --global credential.UseHttpPath true
```

## 📝 재배포 시간 예상

- **CDK Bootstrap**: 3-5분
- **Base Stack**: 5-10분  
- **VPC Stack**: 10-15분 (VPC 엔드포인트 때문에)
- **MLOps Stack**: 15-20분 (SageMaker Studio 때문에)
- **Feature Store 재생성**: 5-10분
- **첫 파이프라인 실행**: 20-30분

**총 예상 시간**: 약 1-1.5시간

## 🎯 최종 확인 명령어

전체 재배포 완료 후 한 번에 확인:
```bash
#!/bin/bash
echo "=== CDK 스택 상태 ==="
cdk list

echo "=== Feature Groups ==="
aws sagemaker list-feature-groups --region ap-northeast-2 --query 'FeatureGroupSummaries[].FeatureGroupName'

echo "=== VPC 엔드포인트 ==="
aws ec2 describe-vpc-endpoints --region ap-northeast-2 --query 'VpcEndpoints[].ServiceName' | wc -l

echo "=== 파이프라인 상태 ==="
aws sagemaker list-pipelines --region ap-northeast-2 --query 'PipelineSummaries[].PipelineName'

echo "=== CodeCommit 저장소 ==="
aws codecommit list-repositories --region ap-northeast-2 --query 'repositories[].repositoryName'

echo "재배포 완료!"
```

이 가이드대로 진행하시면 AWS Nuke 후에도 동일한 환경을 완벽하게 복원할 수 있습니다! 🚀