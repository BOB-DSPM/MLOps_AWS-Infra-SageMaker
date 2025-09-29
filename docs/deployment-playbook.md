# 안전한 배포 플레이북 (AWS SageMaker MLOps)

> **목적**: 개발/운영 환경에 ML 파이프라인을 배포할 때 장애 없이 안정적으로 진행하기 위한 체크리스트와 단계별 절차를 제공합니다.

## 0. 사전 준비
- **AWS 계정/리전**: `ap-northeast-2` (필요 시 `cdk.json` context 확인)
- **IAM 자격**: CDK 배포, CodePipeline/CodeBuild, SageMaker, S3, SNS, CloudWatch 접근이 가능한 역할 사용
- **로컬 환경**
  - Python 3.11, AWS CLI v2, CDK v2 설치
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
- **Git 상태**: `git status`로 작업 디렉터리가 깨끗한지 확인
- **환경 변수** (필요 시 `aws ssm get-parameter` 등으로 동적 조회)
  - `AWS_ACCOUNT_ID`, `AWS_REGION`
  - `DATA_BUCKET`, `SM_EXEC_ROLE_ARN`, `MODEL_PACKAGE_GROUP_NAME`
  - Feature Store 비활성화 시 `USE_FEATURE_STORE=false`

## 1. 로컬 검증
1. **코드 품질 확인**
   ```bash
   pytest  # 테스트 추가 시 실행 권장
   python -m compileall .
   ```
2. **CDK 준비**
   ```bash
   cdk synth
   cdk diff --app "python app.py"  # 주요 스택별 차이점 검토
   ```
   - 리소스 삭제/교체가 필요한 변경은 미리 영향도 분석
3. **구성 파일 점검**
   - `infra/config.py`, `cdk.json`, `stacks/` 내부에서 환경 별 context가 올바른지 확인
   - `buildspec*.yml`의 하드코딩된 버킷/ARN이 실제 목표 환경과 일치하는지 확인(필요 시 환경 변수로 대체)

## 2. 배포 전 체크포인트
- **S3/ECR 잔여 리소스**: 버킷이 잠겨 있거나 이미지가 잠긴 상태인지 확인
- **Feature Store**: 개발 환경에서 운영 Feature Group을 재사용하는지 여부 확인 (`enable_feature_group`, `use_existing_feature_group`)
- **RDS/네트워크**: VPC 엔드포인트 상태 및 보안그룹 규칙 확인
- **파이프라인 권한**: CodeBuild 역할에 SageMaker 권한이 유지되는지 `infra/iam_role.py` 기반으로 검증

## 3. CDK 배포(인프라 변경이 있을 때만)
1. 브랜치 정리 후 커밋 메시지에 배포 목적 명시
2. `cdk deploy --all` 또는 영향 있는 스택만 개별 배포
3. 배포 로그에서 실패 시 즉시 중단하고 CloudFormation 이벤트 확인
4. 완료 후 `aws cloudformation describe-stacks`로 Output 확인 및 `.env`/파이프라인 변수 업데이트

## 4. MLOps 파이프라인 실행
1. **코드 커밋**: CodeCommit 원격(`my-mlops-*-dev`)에 푸시하여 CodePipeline 트리거
2. **CodePipeline 모니터링**
   - `aws codepipeline get-pipeline-state --name <PipelineName>`
   - CodeBuild 로그: CloudWatch Log Group `*-TrainLogs`, `*-DeployLogs`
3. **Train 단계**
   - SageMaker Pipeline을 사용하는지 (`USE_SM_PIPELINE`) 확인
   - 모델 패키지 그룹 등록, Metrics 파일 업로드 여부 검토
4. **Manual Approval 단계**
   - CloudWatch 이벤트 혹은 SNS 알림으로 대기 상태를 확인
   - 승인 전 `list_model_packages`, `describe_model_package`로 메트릭 검증
5. **Deploy 단계**
   - 승인 후 최신 Approved 모델이 엔드포인트에 반영
   - CodeBuild `Deploy` 프로젝트 로그에서 엔드포인트 업데이트 성공 여부 확인

## 5. 배포 검증
- **엔드포인트 상태**:
  ```bash
  aws sagemaker describe-endpoint --endpoint-name <endpoint>
  ```
- **헬스체크 추론**:
  ```bash
  aws sagemaker-runtime invoke-endpoint \
    --endpoint-name <endpoint> \
    --content-type text/csv \
    --body "25,1,0,1,0,0,1,1" \
    output.json && cat output.json
  ```
- **Feature Store** (사용 중이면)
  ```bash
  aws sagemaker describe-feature-group --feature-group-name <fg-name>
  ```
- **CloudWatch 지표**: 오류율, 지연시간, CPU/메모리 모니터링
- **비즈니스 KPI**: AUC·CTR 등의 오프라인/온라인 지표 추적

## 6. 롤백 전략
1. **SageMaker 엔드포인트 롤백**
   - `aws sagemaker list-endpoint-configs`로 이전 버전 파악
   - `aws sagemaker update-endpoint --endpoint-name <endpoint> --endpoint-config-name <previous-config>`
2. **CodePipeline 재시도**: 실패 단계에서 `Retry Stage` 실행
3. **Cross-repo 배포 취소**
   - 프로덕션 CodeCommit에서 문제 커밋 되돌리기
   - 필요 시 SNS 알림으로 담당자 공유
4. **CDK 롤백**
   - CloudFormation 콘솔에서 이전 스택으로 롤백 실행 또는 `cdk deploy` 재실행

## 7. 운영 중 주의사항 & 위험요인
- `buildspec-dev.yml`의 `USE_FEATURE_STORE` 라인에 오타 존재 → CodeBuild 실패 가능성
- 하드코딩된 S3 버킷/ARN은 환경 변경 시 문제 유발 → SSM Parameter Store/Context 변수 활용 권장
- Cross-repo CodeBuild는 수동 승인 없이 운영 레포에 푸시 → 별도 Approval Stage 추가 고려
- Model Package가 Approved 상태가 아니면 Deploy 단계에서 자동 승인 로직이 동작하므로, 메트릭 검토를 꼭 선행해야 함
- 데이터 버전 관리: `EXTERNAL_CSV_URI` 경로가 최신 데이터인지 확인 (Feature Store 사용 시 데이터 Drift 감시 필요)

## 8. 체크리스트 요약
- [ ] Git clean & 태그/브랜치 전략 수립
- [ ] CDK synth/diff 결과 확인
- [ ] CodeBuild 환경 변수/Parameter Store 최신화
- [ ] CodePipeline 실행 로그 모니터링 및 Manual Approval 수행
- [ ] 엔드포인트/Feature Store/모델 패키지 검증
- [ ] 롤백 계획 숙지 및 실행 경로 확보

필요 시 본 문서를 운영 문서(`PROGRESS_STATUS.md`)와 연동하여 실제 배포 기록을 남기세요.
