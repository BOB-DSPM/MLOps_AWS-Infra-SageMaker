# MLOps Pipeline 진행 상황 및 다음 단계

## 현재 상황 요약 (2025-09-18 07:58 기준)

### 해결된 문제들
1. ✅ **Extract 스텝 성공**: Feature Group 생성 및 IAM 권한 추가로 Extract 단계 해결
2. ✅ **Train 스텝 성공**: XGBoost 이미지 URI 수정 (잘못된 계정 ID 366743142698로 수정)
3. ✅ **SageMaker Pipeline 성공**: 전체 파이프라인(Extract→Validate→Preprocess→Train→Evaluate→RegisterModel) 성공

### 현재 문제
- **Deploy 스테이지 실패**: CodePipeline의 Deploy 단계에서 모델 패키지를 찾지 못하는 문제

### 최근 수정사항
1. `stacks/base_stack.py`: XGBoost 이미지 계정 ID 수정 (683313688378 → 366743142698)
2. `infra/sagemaker_ci.py`: Deploy 스크립트 수정 (ModelApprovalStatus 필터 추가)

## 현재 인프라 상태

### AWS 리소스
- **CDK 스택**: My-mlops-BaseStack (배포 완료)
- **SageMaker Pipeline**: mlops-pipeline (성공 실행 완료)
- **Model Registry**: my-mlops-dev-pkg (Approved 모델 2개 있음)
- **Feature Group**: my-mlops-dev-feature-group-ctr (생성 완료)
- **CodePipeline**: my-mlops-repo-pipeline

### 최신 실행 상태
- **SageMaker Pipeline**: arn:aws:sagemaker:ap-northeast-2:651706765732:pipeline/mlops-pipeline/execution/m3ikl5vnghn3 (성공)
- **CodePipeline**: 마지막 실행 ID는 확인 필요
- **Model Packages**: 
  - Version 2: arn:aws:sagemaker:ap-northeast-2:651706765732:model-package/my-mlops-dev-pkg/2 (Approved)
  - Version 1: arn:aws:sagemaker:ap-northeast-2:651706765732:model-package/my-mlops-dev-pkg/1 (Approved)

## 다음 해야 할 작업

### 즉시 확인할 것
1. **CodePipeline 상태 확인**:
   ```bash
   aws codepipeline get-pipeline-state --name my-mlops-repo-pipeline --region ap-northeast-2
   ```

2. **Deploy 스테이지 로그 확인**:
   ```bash
   # Deploy 프로젝트 이름: SmCiCdDeploy401A81C9-PFZUHFPYY0NR
   aws codebuild list-builds-for-project --project-name SmCiCdDeploy401A81C9-PFZUHFPYY0NR --sort-order DESCENDING --max-items 1
   ```

### 예상되는 문제와 해결책

#### 문제 1: Deploy에서 모델 패키지를 찾지 못함
**원인**: Deploy 스크립트가 ModelApprovalStatus='Approved' 필터를 사용하지 않음
**해결**: `infra/sagemaker_ci.py`의 Deploy 스크립트 수정 완료 (재배포 필요할 수 있음)

#### 문제 2: Model Data S3 경로 문제
**원인**: TrainRegister와 SageMaker Pipeline이 서로 다른 경로 사용
**해결책**: 
- Deploy 스크립트가 Model Registry의 모델을 직접 사용하도록 수정
- TrainRegister 단계 비활성화 고려

### 다음 단계별 진행방법

1. **현재 CodePipeline 상태 확인**:
   ```bash
   aws codepipeline get-pipeline-execution --pipeline-name my-mlops-repo-pipeline --pipeline-execution-id [최신ID]
   ```

2. **Deploy 실패 시 로그 분석**:
   ```bash
   # 최신 Deploy 빌드 ID 찾기
   BUILD_ID=$(aws codebuild list-builds-for-project --project-name SmCiCdDeploy401A81C9-PFZUHFPYY0NR --sort-order DESCENDING --max-items 1 --query 'ids[0]' --output text)
   
   # 빌드 상세 정보 확인
   aws codebuild batch-get-builds --ids "$BUILD_ID" --query 'builds[0].logs'
   
   # 로그 확인 (로그 그룹 이름은 위 결과에서 확인)
   aws logs get-log-events --log-group-name [LOG_GROUP] --log-stream-name [STREAM] --query 'events[-20:].message'
   ```

3. **Deploy 스크립트 재수정 필요 시**:
   - `infra/sagemaker_ci.py` 파일의 280-320 라인 Deploy 부분 수정
   - `cdk deploy --require-approval never` 실행

4. **새 파이프라인 실행**:
   ```bash
   aws codepipeline start-pipeline-execution --name my-mlops-repo-pipeline
   ```

## 중요 파일 경로

### 주요 설정 파일
- `stacks/base_stack.py`: 스택 정의 (XGBoost 이미지 URI 설정)
- `infra/sagemaker_ci.py`: CI/CD 설정 (TrainRegister, Deploy 스크립트)
- `infra/sagemaker_exec.py`: SageMaker 실행 역할 (IAM 권한)
- `cdk.json`: CDK 설정 (use_existing_feature_group: false)

### 파이프라인 파일
- `pipelines/pipeline_def.py`: SageMaker 파이프라인 정의
- `pipelines/steps/01_extract.py`: Extract 스크립트 (AWS 리전 설정 포함)

## 트러블슈팅 팁

### Deploy 스크립트 디버깅
Deploy에서 문제 발생 시 다음 사항 확인:
1. MODEL_PACKAGE_GROUP_NAME 환경변수 = "my-mlops-dev-pkg"
2. Model Registry에 Approved 상태 모델 존재 여부
3. S3 model.tar.gz 파일 경로 정확성

### 일반적인 해결 순서
1. 로그 확인 → 2. 스크립트 수정 → 3. CDK 배포 → 4. 파이프라인 재실행

## 마지막 성공한 명령어들
```bash
# 성공한 CDK 배포
cdk deploy --require-approval never

# 성공한 파이프라인 시작
aws codepipeline start-pipeline-execution --name my-mlops-repo-pipeline
```

---
**생성 시각**: 2025-09-18 07:58 KST  
**다음 확인 시점**: CodePipeline 실행 완료 후 (약 5-10분)