# MLOps AWS 프로젝트 Best Practice 참고 링크 모음

## 🏗️ AWS CDK 및 인프라 관련

### AWS CDK 공식 문서
- **CDK Developer Guide**: https://docs.aws.amazon.com/cdk/v2/guide/home.html
- **CDK API Reference**: https://docs.aws.amazon.com/cdk/api/v2/
- **CDK Patterns**: https://cdkpatterns.com/
- **CDK Examples**: https://github.com/aws-samples/aws-cdk-examples

### VPC 및 네트워킹
- **VPC 엔드포인트 구성**: https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints.html
- **SageMaker VPC 설정**: https://docs.aws.amazon.com/sagemaker/latest/dg/infrastructure-give-access.html
- **AWS Private Subnet 베스트 프랙티스**: https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Scenario2.html

## 🤖 SageMaker 및 MLOps 관련

### SageMaker 파이프라인
- **SageMaker Pipelines 개발자 가이드**: https://docs.aws.amazon.com/sagemaker/latest/dg/pipelines.html
- **SageMaker Python SDK**: https://sagemaker.readthedocs.io/en/stable/
- **MLOps 모범 사례**: https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-projects-whatis.html

### Feature Store
- **SageMaker Feature Store**: https://docs.aws.amazon.com/sagemaker/latest/dg/feature-store.html
- **Feature Store 데이터 수집**: https://docs.aws.amazon.com/sagemaker/latest/dg/feature-store-ingest-data.html
- **Feature Store Athena 통합**: https://docs.aws.amazon.com/sagemaker/latest/dg/feature-store-athena.html

### Model Registry
- **SageMaker Model Registry**: https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry.html
- **Model 승인 워크플로우**: https://docs.aws.amazon.com/sagemaker/latest/dg/model-registry-approve.html

## 🔄 CI/CD 및 DevOps 관련

### CodeCommit & CodeBuild
- **CodeCommit 개발자 가이드**: https://docs.aws.amazon.com/codecommit/latest/userguide/welcome.html
- **CodeBuild 사용자 가이드**: https://docs.aws.amazon.com/codebuild/latest/userguide/welcome.html
- **Git Credential Helper**: https://docs.aws.amazon.com/codecommit/latest/userguide/setting-up-git-remote-codecommit.html

### Cross-Repository 배포
- **Git 서브모듈 베스트 프랙티스**: https://git-scm.com/book/en/v2/Git-Tools-Submodules
- **CodeBuild Git 통합**: https://docs.aws.amazon.com/codebuild/latest/userguide/sample-source-version.html

## 🔐 보안 및 IAM 관련

### IAM 정책 및 역할
- **SageMaker IAM 역할**: https://docs.aws.amazon.com/sagemaker/latest/dg/sagemaker-roles.html
- **최소 권한 원칙**: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#grant-least-privilege
- **IAM 정책 예제**: https://docs.aws.amazon.com/sagemaker/latest/dg/security_iam_id-based-policy-examples.html

### KMS 암호화
- **SageMaker 암호화**: https://docs.aws.amazon.com/sagemaker/latest/dg/encryption-at-rest.html
- **KMS 키 관리**: https://docs.aws.amazon.com/kms/latest/developerguide/overview.html

## 📊 모니터링 및 로깅

### CloudWatch
- **SageMaker CloudWatch 메트릭**: https://docs.aws.amazon.com/sagemaker/latest/dg/monitoring-cloudwatch.html
- **CodeBuild 로그 관리**: https://docs.aws.amazon.com/codebuild/latest/userguide/view-build-details.html

### X-Ray 트레이싱
- **AWS X-Ray 개발자 가이드**: https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html

## 🗂️ 데이터 관리 관련

### S3 베스트 프랙티스
- **S3 성능 최적화**: https://docs.aws.amazon.com/AmazonS3/latest/userguide/optimizing-performance.html
- **S3 버전 관리**: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html
- **S3 라이프사이클 정책**: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html

### 데이터 버전 관리
- **ML 데이터 버전 관리**: https://docs.aws.amazon.com/sagemaker/latest/dg/data-prep.html

## 🚀 배포 및 추론 관련

### SageMaker 엔드포인트
- **실시간 추론 엔드포인트**: https://docs.aws.amazon.com/sagemaker/latest/dg/realtime-endpoints.html
- **Auto Scaling**: https://docs.aws.amazon.com/sagemaker/latest/dg/endpoint-auto-scaling.html
- **Multi-Model 엔드포인트**: https://docs.aws.amazon.com/sagemaker/latest/dg/multi-model-endpoints.html

### 컨테이너 관련
- **ECS Fargate**: https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html
- **ECR 베스트 프랙티스**: https://docs.aws.amazon.com/AmazonECR/latest/userguide/best-practices.html

## 🛠️ 개발 도구 및 유틸리티

### AWS CLI
- **AWS CLI 참조**: https://docs.aws.amazon.com/cli/latest/reference/
- **AWS CLI 구성**: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html

### Boto3
- **Boto3 문서**: https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
- **SageMaker Boto3**: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sagemaker.html

## 🧹 리소스 관리 및 정리

### AWS Nuke
- **AWS Nuke GitHub**: https://github.com/rebuy-de/aws-nuke
- **AWS Nuke 설정 가이드**: https://github.com/rebuy-de/aws-nuke#config-file

### Cost 최적화
- **AWS Cost 최적화**: https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html
- **SageMaker Cost 관리**: https://docs.aws.amazon.com/sagemaker/latest/dg/gs-setup-working-env.html

## 📚 추가 학습 리소스

### AWS 교육 자료
- **AWS Machine Learning Learning Path**: https://aws.amazon.com/training/learning-paths/machine-learning/
- **AWS MLOps 워크샵**: https://catalog.workshops.aws/mlops/en-US

### GitHub 예제 및 템플릿
- **AWS SageMaker Examples**: https://github.com/aws/amazon-sagemaker-examples
- **MLOps CDK Patterns**: https://github.com/aws-samples/aws-mlops-framework
- **SageMaker 프로젝트 템플릿**: https://github.com/aws/sagemaker-project-templates

### 커뮤니티 리소스
- **AWS Machine Learning Blog**: https://aws.amazon.com/blogs/machine-learning/
- **SageMaker 개발자 커뮤니티**: https://repost.aws/tags/TAbOw7e3TwRXGlwfRa2M8BDg/amazon-sagemaker

## 🎯 특별히 이 프로젝트에서 적용한 패턴들

### 1. Multi-Stack CDK 아키텍처
- Base Stack: 공통 리소스 (KMS, IAM)
- VPC Stack: 네트워크 격리
- MLOps Stack: SageMaker 및 CI/CD
- Inference Stack: 추론 서비스

### 2. Feature Store 중심 데이터 파이프라인
- CSV → Feature Store → SageMaker Pipeline
- Athena 쿼리를 통한 데이터 접근
- 버전 관리 및 데이터 카탈로그

### 3. Cross-Repository 배포 전략
- Dev → Prod 자동 배포
- CodeBuild를 통한 Git 자동화
- Manual Approval 게이트

### 4. VPC 격리 및 엔드포인트 활용
- Private Subnet에서 AWS 서비스 접근
- 9개 VPC 엔드포인트로 보안 강화
- Network ACL 및 Security Group 설정

### 5. 완전 자동화된 복구 시스템
- AWS Nuke 대응 백업/복구 스크립트
- 인프라 코드 기반 재현 가능한 배포
- 검증 자동화

이러한 패턴들은 모두 AWS 공식 문서와 베스트 프랙티스를 기반으로 구현되었습니다.