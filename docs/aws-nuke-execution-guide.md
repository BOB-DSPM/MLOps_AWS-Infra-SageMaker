# AWS Nuke 실행 가이드

## 📋 AWS Nuke 실행 순서

### 1️⃣ 사전 백업 (필수!)
```bash
# 백업 스크립트 실행
./scripts/pre-nuke-backup.sh

# Git 최신 상태 확인
git status
git add .
git commit -m "AWS Nuke 전 최종 백업"
git push origin main
git push dev main
```

### 2️⃣ AWS Nuke 설정 파일 생성
```yaml
# aws-nuke-config.yml
regions:
- ap-northeast-2

account-blocklist:
- "999999999999"  # 가짜 계정 번호

accounts:
  "651706765732":  # 실제 계정 번호
    filters:
      IAMRole:
      - "AWSServiceRole*"
      - "aws-service-role/*"
      - "OrganizationAccountAccessRole"
      IAMRolePolicy:
      - "AWSServiceRole*"
      S3Bucket:
      - "aws-cloudtrail-logs-*"
      - "aws-logs-*"
```

### 3️⃣ AWS Nuke 실행
```bash
# Dry run으로 먼저 확인
aws-nuke -c aws-nuke-config.yml --profile your-profile --dry-run

# 실제 실행 (주의!)
aws-nuke -c aws-nuke-config.yml --profile your-profile --no-dry-run
```

### 4️⃣ 재배포 실행
```bash
# 자동 재배포 스크립트 실행
./scripts/post-nuke-deploy.sh

# 검증 스크립트 실행
./scripts/verify-deployment.sh
```

## ⚠️ 주의사항

1. **반드시 백업 먼저**: `pre-nuke-backup.sh` 실행 필수
2. **계정 번호 확인**: config 파일의 계정 번호가 정확한지 확인
3. **Dry run 테스트**: 실제 실행 전 dry-run으로 확인
4. **시간 여유**: 재배포에 1-1.5시간 소요

## 🔄 재배포 후 확인사항

- [ ] 모든 CDK 스택 정상 배포
- [ ] Feature Store 데이터 복원
- [ ] VPC 엔드포인트 9개 생성
- [ ] SageMaker Studio 접속 가능
- [ ] 파이프라인 실행 성공
- [ ] 크로스 레포지토리 배포 동작