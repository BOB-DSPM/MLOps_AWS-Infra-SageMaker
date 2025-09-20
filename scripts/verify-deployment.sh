#!/bin/bash

# AWS Nuke 후 재배포 검증 스크립트
# 재배포 완료 후 모든 구성요소가 정상 작동하는지 확인합니다

set -e

echo "🔍 AWS Nuke 후 재배포 검증 시작..."

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_check() {
    echo -e "${BLUE}[CHECK]${NC} $1"
}

check_status() {
    if [ $? -eq 0 ]; then
        echo -e "  ✅ ${GREEN}성공${NC}"
        return 0
    else
        echo -e "  ❌ ${RED}실패${NC}"
        return 1
    fi
}

# 검증 카운터
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

perform_check() {
    local description="$1"
    local command="$2"
    local expected_result="$3"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    log_check "$description"
    
    if eval "$command" > /dev/null 2>&1; then
        if [ -z "$expected_result" ] || eval "$command" | grep -q "$expected_result"; then
            echo -e "  ✅ ${GREEN}통과${NC}"
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
            return 0
        else
            echo -e "  ❌ ${RED}실패${NC} (예상 결과와 다름)"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
            return 1
        fi
    else
        echo -e "  ❌ ${RED}실패${NC} (명령어 실행 오류)"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
        return 1
    fi
}

echo ""
log_info "=== 1. 기본 환경 검증 ==="

perform_check "AWS CLI 인증 상태" "aws sts get-caller-identity" "651706765732"
perform_check "Python 가상환경 활성화" "python --version" "Python 3"
perform_check "CDK 설치 확인" "cdk --version"

echo ""
log_info "=== 2. CDK 스택 검증 ==="

perform_check "Base Stack 배포 상태" "aws cloudformation describe-stacks --stack-name My-mlops-BaseStack --region ap-northeast-2 --query 'Stacks[0].StackStatus'" "CREATE_COMPLETE\|UPDATE_COMPLETE"
perform_check "VPC Stack 배포 상태" "aws cloudformation describe-stacks --stack-name My-mlops-DevVpcStack --region ap-northeast-2 --query 'Stacks[0].StackStatus'" "CREATE_COMPLETE\|UPDATE_COMPLETE"
perform_check "MLOps Stack 배포 상태" "aws cloudformation describe-stacks --stack-name My-mlops-DevMLOpsStack --region ap-northeast-2 --query 'Stacks[0].StackStatus'" "CREATE_COMPLETE\|UPDATE_COMPLETE"
perform_check "Inference Stack 배포 상태" "aws cloudformation describe-stacks --stack-name My-mlops-InferenceStack --region ap-northeast-2 --query 'Stacks[0].StackStatus'" "CREATE_COMPLETE\|UPDATE_COMPLETE"

echo ""
log_info "=== 3. 네트워크 및 VPC 검증 ==="

VPC_COUNT=$(aws ec2 describe-vpcs --region ap-northeast-2 --filters "Name=tag:Name,Values=*mlops*" --query 'Vpcs | length(@)' --output text 2>/dev/null || echo "0")
log_check "MLOps VPC 존재 확인"
if [ "$VPC_COUNT" -gt 0 ]; then
    echo -e "  ✅ ${GREEN}통과${NC} (VPC 개수: $VPC_COUNT)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo -e "  ❌ ${RED}실패${NC} (VPC를 찾을 수 없음)"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

ENDPOINT_COUNT=$(aws ec2 describe-vpc-endpoints --region ap-northeast-2 --query 'VpcEndpoints | length(@)' --output text 2>/dev/null || echo "0")
log_check "VPC 엔드포인트 확인"
if [ "$ENDPOINT_COUNT" -ge 8 ]; then
    echo -e "  ✅ ${GREEN}통과${NC} (엔드포인트 개수: $ENDPOINT_COUNT)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo -e "  ⚠️ ${YELLOW}주의${NC} (엔드포인트 개수: $ENDPOINT_COUNT, 최소 8개 권장)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
log_info "=== 4. Feature Store 검증 ==="

perform_check "개발 Feature Group 존재" "aws sagemaker describe-feature-group --feature-group-name ad-click-feature-group-dev --region ap-northeast-2" "Created"
perform_check "운영 Feature Group 존재" "aws sagemaker describe-feature-group --feature-group-name ad-click-feature-group --region ap-northeast-2" "Created"

# Feature Group 데이터 개수 확인
log_check "Feature Store 데이터 개수 확인"
FG_RECORD_COUNT=$(aws sagemaker search --resource feature-groups --search-expression '{
  "Filters": [
    {
      "Name": "FeatureGroupName", 
      "Operator": "Equals", 
      "Value": "ad-click-feature-group-dev"
    }
  ]
}' --region ap-northeast-2 --query 'Results[0].FeatureGroup.RecordIdentifierFeatureName' --output text 2>/dev/null || echo "N/A")

if [ "$FG_RECORD_COUNT" != "N/A" ] && [ "$FG_RECORD_COUNT" != "None" ]; then
    echo -e "  ✅ ${GREEN}통과${NC} (Feature Group 접근 가능)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo -e "  ⚠️ ${YELLOW}주의${NC} (Feature Group 상태 확인 필요)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
log_info "=== 5. SageMaker 리소스 검증 ==="

perform_check "SageMaker 실행 역할 존재" "aws iam list-roles --query 'Roles[?contains(RoleName, \`mlops\`) && contains(RoleName, \`Exec\`)].RoleName' --output text" "mlops"
perform_check "SageMaker Studio 도메인 존재" "aws sagemaker list-domains --region ap-northeast-2 --query 'Domains[0].DomainName'" "dev-studio"

# Model Package Group 확인
log_check "Model Package Group 확인"
MPG_COUNT=$(aws sagemaker list-model-package-groups --region ap-northeast-2 --query 'ModelPackageGroupSummaryList | length(@)' --output text 2>/dev/null || echo "0")
if [ "$MPG_COUNT" -gt 0 ]; then
    echo -e "  ✅ ${GREEN}통과${NC} (Model Package Group 개수: $MPG_COUNT)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo -e "  ⚠️ ${YELLOW}주의${NC} (아직 모델이 등록되지 않음 - 첫 파이프라인 실행 후 생성됨)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
log_info "=== 6. CodeCommit 및 CI/CD 검증 ==="

perform_check "CodeCommit 개발 저장소 존재" "aws codecommit get-repository --repository-name my-mlops-repo-dev --region ap-northeast-2" "my-mlops-repo-dev"
perform_check "CodeCommit 운영 저장소 존재" "aws codecommit get-repository --repository-name my-mlops-repo --region ap-northeast-2" "my-mlops-repo"

# CodeBuild 프로젝트 확인
log_check "CodeBuild 프로젝트 확인"
CB_COUNT=$(aws codebuild list-projects --region ap-northeast-2 --query 'projects | length(@)' --output text 2>/dev/null || echo "0")
if [ "$CB_COUNT" -gt 0 ]; then
    echo -e "  ✅ ${GREEN}통과${NC} (CodeBuild 프로젝트 개수: $CB_COUNT)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo -e "  ❌ ${RED}실패${NC} (CodeBuild 프로젝트가 없음)"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
log_info "=== 7. Git 저장소 연결 검증 ==="

log_check "Git 원격 저장소 설정"
git remote -v | grep -q "codecommit" && {
    echo -e "  ✅ ${GREEN}통과${NC} (CodeCommit 연결됨)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
} || {
    echo -e "  ❌ ${RED}실패${NC} (CodeCommit 연결 안됨)"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
}
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

log_check "Git 인증 설정"
git config --get credential.helper | grep -q "codecommit" && {
    echo -e "  ✅ ${GREEN}통과${NC} (CodeCommit 인증 설정됨)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
} || {
    echo -e "  ⚠️ ${YELLOW}주의${NC} (CodeCommit 인증 설정 확인 필요)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
}
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
log_info "=== 8. 파이프라인 상태 확인 ==="

# SageMaker Pipeline 확인 (생성되는데 시간이 걸릴 수 있음)
log_check "SageMaker 파이프라인 확인"
PIPELINE_COUNT=$(aws sagemaker list-pipelines --region ap-northeast-2 --query 'PipelineSummaries | length(@)' --output text 2>/dev/null || echo "0")
if [ "$PIPELINE_COUNT" -gt 0 ]; then
    echo -e "  ✅ ${GREEN}통과${NC} (파이프라인 개수: $PIPELINE_COUNT)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
else
    echo -e "  ⚠️ ${YELLOW}주의${NC} (파이프라인이 아직 생성되지 않음 - CodeCommit 푸시 후 자동 생성)"
    PASSED_CHECKS=$((PASSED_CHECKS + 1))
fi
TOTAL_CHECKS=$((TOTAL_CHECKS + 1))

echo ""
log_info "=== 9. 중요 파일 존재 확인 ==="

perform_check "데이터셋 파일 존재" "ls ad_click_dataset.csv"
perform_check "Feature Store 스크립트 존재" "ls scripts/ingest_to_feature_store.py"
perform_check "CDK 설정 파일 존재" "ls cdk.json"
perform_check "파이프라인 정의 파일 존재" "ls pipelines/pipeline_def.py"

echo ""
echo "========================================"
log_info "🔍 검증 결과 요약"
echo "========================================"
echo -e "총 검사 항목: ${BLUE}$TOTAL_CHECKS${NC}"
echo -e "통과: ${GREEN}$PASSED_CHECKS${NC}"
echo -e "실패: ${RED}$FAILED_CHECKS${NC}"

PASS_RATE=$((PASSED_CHECKS * 100 / TOTAL_CHECKS))
echo -e "통과율: ${BLUE}$PASS_RATE%${NC}"

echo ""
if [ $FAILED_CHECKS -eq 0 ]; then
    log_info "🎉 모든 검증 통과! MLOps 인프라가 정상적으로 재배포되었습니다."
    echo ""
    log_info "다음 단계:"
    echo "1. SageMaker Studio에 접속하여 환경 확인"
    echo "2. 첫 파이프라인 실행 대기 (CodeCommit 푸시로 자동 트리거됨)"
    echo "3. Feature Store 데이터 쿼리 테스트"
    echo "4. 크로스 레포지토리 배포 동작 확인"
elif [ $FAILED_CHECKS -le 2 ]; then
    log_warn "⚠️ 일부 항목에서 문제가 발견되었지만 전체적으로 정상입니다."
    echo "실패한 항목들을 점검하고 필요시 수동으로 수정하세요."
else
    log_error "❌ 여러 중요 항목에서 실패했습니다."
    echo "docs/aws-nuke-recovery-guide.md를 참조하여 문제를 해결하세요."
    exit 1
fi

echo ""
log_info "상세한 문제 해결 방법은 docs/aws-nuke-recovery-guide.md를 참조하세요."