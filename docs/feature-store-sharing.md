# Feature Store 공유 설정 변경사항

## 🔄 변경 내용

### 기존: Dev/Prod 환경별 독립적인 Feature Store
- 개발: `my-mlops-dev-feature-group-v2`
- 운영: `my-mlops-feature-group-v2`

### 변경: 운영 Feature Store 공유 사용
- 개발/운영 모두: `my-mlops-feature-group-v2` 사용
- 사용자 상호작용: `my-mlops-user-interactions-v1` 공유

## 📁 수정된 파일들

### 1. `stacks/dev_mlops_stack.py`
```python
# Feature Store 설정 변경
enable_feature_group = False  # 새로 생성하지 않음
use_existing_feature_group = True  # 운영 Feature Store 참조
feature_group_name = "my-mlops-feature-group-v2"  # 운영과 동일한 이름

# 권한 추가
sm_exec.role.add_to_policy(iam_cdk.PolicyStatement(
    actions=["sagemaker:DescribeFeatureGroup", "sagemaker:PutRecord", ...],
    resources=["arn:aws:sagemaker:*:*:feature-group/my-mlops-*"],
))
```

### 2. `stacks/base_stack.py`
```python
# 운영 Feature Store 활성화
enable_feature_group = True
use_existing_feature_group = False
feature_group_name = "my-mlops-feature-group-v2"  # 고정 이름
```

### 3. `cdk.json`
```json
{
    "feature_group_name": "my-mlops-feature-group-v2",
    "use_existing_feature_group": true
}
```

## ✅ 장점

1. **비용 절약**: Feature Store 하나만 운영
2. **데이터 일관성**: 동일한 데이터 소스 사용
3. **관리 단순화**: 하나의 Feature Store만 관리
4. **실시간 동기화**: 별도 동기화 프로세스 불필요

## ⚠️ 주의사항

1. **권한 관리**: 개발팀이 운영 데이터에 접근 가능
2. **데이터 품질**: 개발 실험이 운영 데이터에 영향 가능
3. **성능 영향**: 개발 부하가 운영에 영향 줄 수 있음

## 🚀 배포 방법

```bash
# 변경사항 배포
cdk deploy --all

# Feature Store 상태 확인
aws sagemaker list-feature-groups --feature-group-status-equals Created

# 권한 테스트
aws sagemaker describe-feature-group --feature-group-name my-mlops-feature-group-v2
```

## 🔙 롤백 방법

개별 Feature Store로 되돌리려면:

1. `dev_mlops_stack.py`에서 `enable_feature_group = True`
2. `feature_group_name = f"{name_prefix}-feature-group-v2"`로 변경
3. `cdk deploy` 실행
