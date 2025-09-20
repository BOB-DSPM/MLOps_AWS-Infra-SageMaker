#!/bin/bash

# AWS Nuke 사전 백업 스크립트
# 실행 전에 반드시 이 스크립트를 실행하여 중요 데이터를 백업하세요

set -e

echo "🔄 AWS Nuke 사전 백업 시작..."

# 백업 디렉토리 생성
BACKUP_DIR="backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p $BACKUP_DIR

echo "📁 백업 디렉토리: $BACKUP_DIR"

# 1. Git 저장소 상태 확인 및 백업
echo "📦 Git 저장소 백업 중..."
git status > $BACKUP_DIR/git-status.txt
git log --oneline -n 10 > $BACKUP_DIR/git-log.txt
git remote -v > $BACKUP_DIR/git-remotes.txt

# 2. 현재 AWS 구성 백업
echo "☁️ AWS 구성 백업 중..."
aws sts get-caller-identity > $BACKUP_DIR/aws-identity.json 2>/dev/null || echo "AWS CLI 인증 실패"

# 3. CloudFormation 스택 정보 백업
echo "📚 CloudFormation 스택 백업 중..."
aws cloudformation list-stacks --region ap-northeast-2 > $BACKUP_DIR/cloudformation-stacks.json 2>/dev/null || echo "CloudFormation 백업 실패"

# 4. Feature Groups 정보 백업
echo "🗂️ Feature Groups 백업 중..."
aws sagemaker list-feature-groups --region ap-northeast-2 > $BACKUP_DIR/feature-groups.json 2>/dev/null || echo "Feature Groups 백업 실패"

# 5. S3 버킷 리스트 백업
echo "🪣 S3 버킷 리스트 백업 중..."
aws s3 ls > $BACKUP_DIR/s3-buckets.txt 2>/dev/null || echo "S3 백업 실패"

# 6. VPC 정보 백업
echo "🌐 VPC 정보 백업 중..."
aws ec2 describe-vpcs --region ap-northeast-2 > $BACKUP_DIR/vpcs.json 2>/dev/null || echo "VPC 백업 실패"
aws ec2 describe-vpc-endpoints --region ap-northeast-2 > $BACKUP_DIR/vpc-endpoints.json 2>/dev/null || echo "VPC 엔드포인트 백업 실패"

# 7. 중요 파일들 백업
echo "📄 중요 파일 백업 중..."
cp -r infra/ $BACKUP_DIR/ 2>/dev/null || echo "infra 디렉토리 백업 실패"
cp -r stacks/ $BACKUP_DIR/ 2>/dev/null || echo "stacks 디렉토리 백업 실패"
cp -r pipelines/ $BACKUP_DIR/ 2>/dev/null || echo "pipelines 디렉토리 백업 실패"
cp *.py $BACKUP_DIR/ 2>/dev/null || echo "Python 파일 백업 실패"
cp *.json $BACKUP_DIR/ 2>/dev/null || echo "JSON 파일 백업 실패"
cp *.md $BACKUP_DIR/ 2>/dev/null || echo "Markdown 파일 백업 실패"
cp ad_click_dataset.csv $BACKUP_DIR/ 2>/dev/null || echo "데이터셋 파일 백업 실패"

# 8. CDK 정보 백업
echo "🏗️ CDK 정보 백업 중..."
cdk list > $BACKUP_DIR/cdk-stacks.txt 2>/dev/null || echo "CDK 리스트 백업 실패"

echo "✅ 백업 완료! 백업 위치: $BACKUP_DIR"
echo ""
echo "🚨 중요한 확인사항:"
echo "1. Git 저장소가 최신 상태인지 확인: git status"
echo "2. 모든 변경사항이 푸시되었는지 확인: git push origin main && git push dev main"
echo "3. Feature Store 데이터가 ad_click_dataset.csv에 보관되어 있는지 확인"
echo ""
echo "이제 AWS Nuke를 안전하게 실행할 수 있습니다."