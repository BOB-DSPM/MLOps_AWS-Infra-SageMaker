#!/bin/bash

# AWS Nuke 후 자동 재배포 스크립트
# 이 스크립트는 AWS Nuke 실행 후 전체 MLOps 인프라를 자동으로 재배포합니다

set -e

echo "🚀 AWS Nuke 후 MLOps 인프라 재배포 시작..."

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 함수 정의
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

wait_for_completion() {
    local description="$1"
    local check_command="$2"
    local max_attempts=30
    local attempt=1
    
    log_info "$description 대기 중..."
    while [ $attempt -le $max_attempts ]; do
        if eval "$check_command"; then
            log_info "$description 완료!"
            return 0
        fi
        echo "  시도 $attempt/$max_attempts - 30초 대기..."
        sleep 30
        attempt=$((attempt + 1))
    done
    
    log_error "$description 시간 초과!"
    return 1
}

# Step 1: 기본 환경 확인
log_info "=== Step 1: 기본 환경 확인 ==="

# Python 가상환경 활성화
if [ ! -d ".venv" ]; then
    log_info "Python 가상환경 생성 중..."
    python3 -m venv .venv
fi

log_info "가상환경 활성화 중..."
source .venv/bin/activate

log_info "Python 패키지 설치 중..."
pip install -r requirements.txt

# AWS 설정 확인
log_info "AWS 설정 확인 중..."
aws sts get-caller-identity || {
    log_error "AWS 인증 실패! aws configure를 실행하세요."
    exit 1
}

# Step 2: CDK Bootstrap
log_info "=== Step 2: CDK Bootstrap ==="
log_info "CDK Bootstrap 실행 중..."
cdk bootstrap aws://651706765732/ap-northeast-2

# Step 3: 순차적 스택 배포
log_info "=== Step 3: CDK 스택 배포 ==="

# Base Stack 배포
log_info "Base Stack 배포 중..."
cdk deploy My-mlops-BaseStack --require-approval never
log_info "✅ Base Stack 배포 완료"

# VPC Stack 배포
log_info "VPC Stack 배포 중 (10-15분 소요 예상)..."
cdk deploy My-mlops-DevVpcStack --require-approval never
log_info "✅ VPC Stack 배포 완료"

# MLOps Stack 배포
log_info "MLOps Stack 배포 중 (15-20분 소요 예상)..."
cdk deploy My-mlops-DevMLOpsStack --require-approval never
log_info "✅ MLOps Stack 배포 완료"

# Inference Stack 배포 (선택사항)
log_info "Inference Stack 배포 중..."
cdk deploy My-mlops-InferenceStack --require-approval never
log_info "✅ Inference Stack 배포 완료"

# Step 4: Feature Store 재생성
log_info "=== Step 4: Feature Store 재생성 ==="

# CSV 파일 확인
if [ ! -f "ad_click_dataset.csv" ]; then
    log_error "ad_click_dataset.csv 파일이 없습니다!"
    log_info "백업에서 복원하거나 다시 다운로드하세요."
    exit 1
fi

log_info "Feature Store 생성 중..."
python scripts/ingest_to_feature_store.py

# Feature Store 생성 확인
wait_for_completion "Feature Store 생성" \
    "aws sagemaker describe-feature-group --feature-group-name ad-click-feature-group-dev --region ap-northeast-2 --query 'FeatureGroupStatus' --output text | grep -q 'Created'"

# Step 5: CodeCommit 저장소 재연결
log_info "=== Step 5: CodeCommit 저장소 재연결 ==="

# 기존 원격 저장소 제거 (에러 무시)
git remote remove aws 2>/dev/null || true
git remote remove dev 2>/dev/null || true

# 새로운 CodeCommit 저장소 추가
log_info "CodeCommit 원격 저장소 추가 중..."
git remote add aws https://git-codecommit.ap-northeast-2.amazonaws.com/v1/repos/my-mlops-repo
git remote add dev https://git-codecommit.ap-northeast-2.amazonaws.com/v1/repos/my-mlops-repo-dev

# Git credential helper 설정
git config --global credential.helper '!aws codecommit credential-helper $@'
git config --global credential.UseHttpPath true

# 첫 푸시
log_info "CodeCommit에 코드 푸시 중..."
git push aws main
git push dev main

# Step 6: 파이프라인 테스트
log_info "=== Step 6: 파이프라인 테스트 ==="

# 파이프라인 트리거를 위한 더미 커밋
echo "# AWS Nuke 후 재배포 완료 - $(date)" >> PROGRESS_STATUS.md
git add PROGRESS_STATUS.md
git commit -m "🚀 AWS Nuke 후 자동 재배포 완료 - $(date +%Y-%m-%d)"
git push dev main

log_info "파이프라인 트리거 완료! CodeCommit 푸시로 자동 실행됩니다."

# Step 7: 배포 상태 확인
log_info "=== Step 7: 배포 상태 확인 ==="

sleep 10

log_info "CDK 스택 상태:"
cdk list

log_info "Feature Groups 확인:"
aws sagemaker list-feature-groups --region ap-northeast-2 --query 'FeatureGroupSummaries[].FeatureGroupName' --output table

log_info "VPC 엔드포인트 확인:"
ENDPOINT_COUNT=$(aws ec2 describe-vpc-endpoints --region ap-northeast-2 --query 'VpcEndpoints[].ServiceName' --output text | wc -w)
echo "VPC 엔드포인트 개수: $ENDPOINT_COUNT"

log_info "CodeCommit 저장소 확인:"
aws codecommit list-repositories --region ap-northeast-2 --query 'repositories[].repositoryName' --output table

# 파이프라인 확인 (시간이 걸릴 수 있음)
sleep 30
log_info "SageMaker 파이프라인 확인:"
aws sagemaker list-pipelines --region ap-northeast-2 --query 'PipelineSummaries[].PipelineName' --output table 2>/dev/null || log_warn "파이프라인이 아직 생성되지 않았습니다. CodeCommit 푸시 후 자동 생성됩니다."

echo ""
log_info "🎉 AWS Nuke 후 재배포 완료!"
echo ""
log_info "다음 단계:"
echo "1. SageMaker Studio 확인: AWS Console에서 SageMaker Studio 접속"
echo "2. 파이프라인 실행 모니터링: 약 20-30분 후 첫 파이프라인 실행 완료"
echo "3. Feature Store 데이터 확인: Athena에서 쿼리 테스트"
echo "4. 크로스 레포지토리 배포 테스트: 운영 레포에 자동 커밋 확인"
echo ""
log_info "문제가 발생하면 docs/aws-nuke-recovery-guide.md를 참조하세요."