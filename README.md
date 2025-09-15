# MLOps on AWS (SageMaker + CodePipeline)

## 준비
1) `.env.example`를 복사해 `.env` 생성 후 실제 값 입력 (커밋 금지)
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