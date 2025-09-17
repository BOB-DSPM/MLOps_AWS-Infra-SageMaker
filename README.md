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

