# Feature Store 업데이트 안내

기존 Feature Group `my-mlops-dev-feature-group`는 스키마가 `feature1, feature2`로 생성되어 CTR 컬럼과 불일치합니다. SageMaker Feature Store는 스키마 변경 중 "추가"만 허용하며, 일부 경우 콘솔/CLI에서 즉시 반영이 지연될 수 있습니다.

본 레포는 CDK 기본 스키마를 CTR(`gender, age, device, hour, click`)로 수정했고, 충돌을 피하기 위해 새로운 Feature Group 이름(`my-mlops-dev-feature-group-ctr`)을 기본값으로 설정했습니다. 필요한 경우 아래 중 하나를 선택하세요.

- 권장: 새 Feature Group으로 전환
  - `cdk deploy` 후 `my-mlops-dev-feature-group-ctr`로 데이터 적재/파이프라인 실행
- 기존 FG 유지: 스크립트가 자동으로 누락된 CTR 컬럼을 추가하지만, 반영 지연 시 재시도 필요

정리:
- CDK 스키마: CTR 컬럼으로 고정
- 기존 FG: 필요 시 삭제 후 재생성하거나, 새 FG 이름 사용 권장
 