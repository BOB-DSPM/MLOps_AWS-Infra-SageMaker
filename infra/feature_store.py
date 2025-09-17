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
            "DisableGlueTableCreation": False,
        }
        if kms_key_arn:
            offline_cfg["S3StorageConfig"]["KmsKeyId"] = kms_key_arn

        self.feature_group = sagemaker.CfnFeatureGroup(
            self,
            "FeatureGroup",
            feature_group_name=feature_group_name,
            record_identifier_feature_name=record_identifier_name,
            event_time_feature_name=event_time_name,
            feature_definitions=feature_definitions,
            role_arn=role.role_arn,
            online_store_config={"EnableOnlineStore": True},
            offline_store_config=offline_cfg,
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
