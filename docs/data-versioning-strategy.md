# 데이터 버전 관리 전략

## 문제점들과 해결방안

### 1. 데이터 일관성 문제
**문제**: Feature Store 데이터가 지속적으로 업데이트되어 재현성 보장 어려움

**해결방안**:
```python
# 스냅샷 기반 접근
def create_data_snapshot(feature_group_name, timestamp):
    """특정 시점의 데이터 스냅샷 생성"""
    query = f"""
    SELECT * FROM {feature_group_name} 
    WHERE event_time <= '{timestamp}'
    INTO TABLE {feature_group_name}_snapshot_{timestamp}
    """
    return execute_athena_query(query)

# 파이프라인에서 사용
snapshot_id = create_data_snapshot("ad-click-feature-group-dev", "2025-09-19T12:00:00")
```

### 2. S3 Lifecycle 문제
**문제**: 90일 후 모델 아티팩트 자동 삭제로 배포 불가

**해결방안**:
```python
# 중요 모델은 별도 버킷에 영구 보관
def archive_production_model(model_package_arn):
    """승인된 모델은 장기 보관 버킷으로 복사"""
    model_data_url = get_model_data_url(model_package_arn)
    archive_location = f"s3://my-mlops-model-archive/{model_package_arn}/"
    copy_s3_object(model_data_url, archive_location)
    update_model_package_url(model_package_arn, archive_location)
```

### 3. 환경 간 불일치 문제
**문제**: 개발/운영 간 다른 데이터셋 사용

**해결방안**:
```python
# 데이터 일관성 검증
def validate_data_consistency(dev_fg, prod_fg):
    """개발/운영 데이터 분포 비교"""
    dev_stats = get_feature_statistics(dev_fg)
    prod_stats = get_feature_statistics(prod_fg)
    
    if statistical_distance(dev_stats, prod_stats) > threshold:
        raise DataInconsistencyError("Dev/Prod data distribution mismatch")
```

### 4. 동시성 문제
**문제**: 동시 파이프라인 실행 시 데이터 경합

**해결방안**:
```python
# 파이프라인별 격리된 데이터 경로
def get_pipeline_data_path(pipeline_execution_id, step_name):
    """파이프라인 실행별 독립적인 데이터 경로"""
    return f"s3://bucket/pipelines/{pipeline_execution_id}/{step_name}/"
```

## 권장 아키텍처 개선사항

### 1. 데이터 버전 관리
- Delta Lake 또는 Apache Iceberg 도입
- Time Travel 기능으로 특정 시점 데이터 접근
- 스키마 진화 관리

### 2. 모델 아티팩트 관리  
- 승인된 모델은 별도 아카이브 버킷
- Model Registry에 메타데이터와 실제 경로 분리
- 버전별 태깅 시스템

### 3. 환경 격리
- 개발/스테이징/운영 환경별 완전 분리
- 데이터 동기화 정책 수립
- 환경 간 데이터 일관성 모니터링

### 4. 모니터링 및 알림
- 참조 무결성 체크
- S3 객체 존재 여부 모니터링  
- 데이터 드리프트 감지
