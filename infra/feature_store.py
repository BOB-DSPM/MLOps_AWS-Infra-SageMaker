from constructs import Construct
from aws_cdk import (
    aws_sagemaker as sagemaker,
    aws_iam as iam,
    Stack,
)

class FeatureGroup(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        feature_group_name: str,
        s3_uri: str,
        role: iam.IRole,
        kms_key_arn: str | None = None,
        record_identifier_name: str = "id",
        event_time_name: str = "event_time",
        feature_definitions: list = None,
    ):
        super().__init__(scope, id)

        if feature_definitions is None:
            feature_definitions = [
                sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                    feature_name=record_identifier_name, feature_type="Integral"
                ),
                sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                    feature_name=event_time_name, feature_type="String"
                ),
                sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                    feature_name="gender", feature_type="Integral"
                ),
                sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                    feature_name="age", feature_type="Integral"
                ),
                sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                    feature_name="device", feature_type="Integral"
                ),
                sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                    feature_name="hour", feature_type="Integral"
                ),
                sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                    feature_name="click", feature_type="Integral"
                ),
            ]

        offline_cfg = {
            "S3StorageConfig": {"S3Uri": s3_uri},
        }
        if kms_key_arn:
            offline_cfg["S3StorageConfig"]["KmsKeyId"] = kms_key_arn

        online_cfg = {
            "EnableOnlineStore": True,
        }
        if kms_key_arn:
            online_cfg["SecurityConfig"] = {"KmsKeyId": kms_key_arn}

        self.feature_group = sagemaker.CfnFeatureGroup(
            self,
            "FeatureGroup",
            feature_group_name=feature_group_name,
            record_identifier_feature_name=record_identifier_name,
            event_time_feature_name=event_time_name,
            feature_definitions=feature_definitions,
            offline_store_config=offline_cfg,
            online_store_config=online_cfg,
            role_arn=role.role_arn,
        )

        self.feature_group.node.add_dependency(role)
        try:
            default_policy = role.node.try_find_child("DefaultPolicy")
            if default_policy is not None:
                self.feature_group.node.add_dependency(default_policy)
        except Exception:
            pass

        self.feature_group_name = feature_group_name
        self.feature_group_arn = Stack.of(self).format_arn(
            service="sagemaker",
            resource="feature-group",
            resource_name=feature_group_name,
        )


class UserInteractionFeatureGroup(Construct):
    """사용자 상호작용 데이터를 위한 Feature Group"""
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        feature_group_name: str,
        s3_uri: str,
        role: iam.IRole,
        kms_key_arn: str | None = None,
        record_identifier_name: str = "interaction_id",
        event_time_name: str = "event_time",
    ):
        super().__init__(scope, id)

        # 사용자 상호작용 데이터 스키마 정의
        feature_definitions = [
            # 기본 식별자들
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name=record_identifier_name, feature_type="String"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name=event_time_name, feature_type="String"
            ),
            # 예측 요청 데이터
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="user_age", feature_type="Fractional"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="ad_position", feature_type="Fractional"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="browsing_history", feature_type="Fractional"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="time_of_day", feature_type="Fractional"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="user_behavior_score", feature_type="Fractional"
            ),
            # 예측 결과
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="predicted_probability", feature_type="Fractional"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="predicted_class", feature_type="Integral"
            ),
            # 세션 정보
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="session_id", feature_type="String"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="request_type", feature_type="String"  # 'prediction' 또는 'chat'
            ),
            # 챗봇 데이터 (선택적)
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="chat_query_length", feature_type="Integral"
            ),
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="chat_category", feature_type="String"  # 질문 카테고리
            ),
            # 성능 메트릭
            sagemaker.CfnFeatureGroup.FeatureDefinitionProperty(
                feature_name="response_time_ms", feature_type="Fractional"
            ),
        ]

        offline_cfg = {
            "S3StorageConfig": {"S3Uri": s3_uri},
        }
        if kms_key_arn:
            offline_cfg["S3StorageConfig"]["KmsKeyId"] = kms_key_arn

        online_cfg = {
            "EnableOnlineStore": True,
        }
        if kms_key_arn:
            online_cfg["SecurityConfig"] = {"KmsKeyId": kms_key_arn}

        self.feature_group = sagemaker.CfnFeatureGroup(
            self,
            "UserInteractionFeatureGroup",
            feature_group_name=feature_group_name,
            record_identifier_feature_name=record_identifier_name,
            event_time_feature_name=event_time_name,
            feature_definitions=feature_definitions,
            offline_store_config=offline_cfg,
            online_store_config=online_cfg,
            role_arn=role.role_arn,
        )

        self.feature_group.node.add_dependency(role)
        try:
            default_policy = role.node.try_find_child("DefaultPolicy")
            if default_policy is not None:
                self.feature_group.node.add_dependency(default_policy)
        except Exception:
            pass

        self.feature_group_name = feature_group_name
        self.feature_group_arn = Stack.of(self).format_arn(
            service="sagemaker",
            resource="feature-group",
            resource_name=feature_group_name,
        )
