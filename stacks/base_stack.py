from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput,
    aws_iam as iam_cdk,
)
from infra.config import Config
from infra.network import BaseNetwork
from infra.kms_key import BaseKms
from infra.storage import BaseStorage
from infra.ecr_repo import BaseEcr
from infra.iam_role import CiCdIam
from infra.cicd import CiCdPipeline
from infra.sagemaker_exec import SmExecutionRole
from infra.sagemaker_ci import ModelRegistry, SageMakerCiCd
from infra.feature_store import FeatureGroup
from infra.studio import Studio


def _sanitize_alias_component(s: str) -> str:
    """KMS Alias 허용문자(a-zA-Z0-9:/_-) 외 문자는 '-'로 치환"""
    import re
    return re.sub(r"[^a-zA-Z0-9:/_-]", "-", s)


class BaseStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        cfg: Config,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        name_prefix = f"{cfg.project_name}-{cfg.env_name}".lower()
        alias_name = f"alias/{_sanitize_alias_component(name_prefix)}-s3"

        vpc = None
        if cfg.include_vpc:
            net = BaseNetwork(self, "Net")
            vpc = net.vpc

        kms = BaseKms(self, "Kms", alias=alias_name)

        storage = BaseStorage(
            self, "Storage",
            project=cfg.project_name,
            env=cfg.env_name,
            kms_key=kms.key,
            artifact_lifecycle_days=cfg.artifact_bucket_lifecycle_days,
        )

        ecr = BaseEcr(
            self, "Ecr",
            name=f"{cfg.project_name}-{cfg.env_name}".lower(),
            keep_untagged=cfg.ecr_untagged_keep,
        )

        iam = CiCdIam(
            self, "CiCdIam",
            artifacts_bucket_arn=storage.artifacts_bucket.bucket_arn,
            data_bucket_arn=storage.data_bucket.bucket_arn,
            kms_key_arn=kms.key.key_arn,
            ecr_repo_arn=ecr.repo.repository_arn,
        )

        cicd = None
        if cfg.enable_pipeline:
            cicd = CiCdPipeline(
                self, "CiCd",
                repo_name=cfg.codecommit_repo_name,
                branch=cfg.pipeline_branch,
                artifacts_bucket=storage.artifacts_bucket,
                codebuild_role=iam.codebuild_role,
                pipeline_role=iam.pipeline_role,
            )
            CfnOutput(self, "CodeCommitCloneUrlHttp", value=cicd.repo.repository_clone_url_http)
            CfnOutput(self, "PipelineName", value=cicd.pipeline.pipeline_name)

        sm_exec = SmExecutionRole(
            self, "SmExecRole",
            data_bucket=storage.data_bucket,
            artifacts_bucket=storage.artifacts_bucket,
            kms_key=kms.key,
        )

        storage.data_bucket.add_to_resource_policy(iam_cdk.PolicyStatement(
            principals=[iam_cdk.ArnPrincipal(sm_exec.role.role_arn)],
            actions=[
                "s3:GetBucketAcl",
                "s3:GetBucketLocation",
                "s3:ListBucket",
            ],
            resources=[storage.data_bucket.bucket_arn],
        ))
        storage.data_bucket.add_to_resource_policy(iam_cdk.PolicyStatement(
            principals=[iam_cdk.ArnPrincipal(sm_exec.role.role_arn)],
            actions=[
                "s3:GetObject",
                "s3:PutObject",
                "s3:PutObjectAcl",
            ],
            resources=[storage.data_bucket.arn_for_objects("feature-store/*")],
        ))

        fg = FeatureGroup(
            self,
            "FeatureGroup",
            feature_group_name=f"{name_prefix}-feature-group",
            s3_uri=f"s3://{storage.data_bucket.bucket_name}/feature-store/",
            role=sm_exec.role,
            kms_key_arn=kms.key.key_arn,
            record_identifier_name="id",
            event_time_name="event_time",
        )

        if storage.data_bucket.policy:
            fg.feature_group.node.add_dependency(storage.data_bucket.policy)

        enable_sm_ci = bool(self.node.try_get_context("enable_sagemaker_ci") or False)
        if enable_sm_ci and cicd is not None:
            sm_pkg_group_name = self.node.try_get_context("sm_pkg_group_name") or f"{name_prefix}-pkg"
            sm_endpoint_name  = self.node.try_get_context("sm_endpoint_name")  or f"{name_prefix}-endpoint"
            sm_instance_type  = self.node.try_get_context("sm_instance_type")  or "ml.m5.large"
            sm_train_image    = self.node.try_get_context("sm_training_image_uri")

            if not sm_train_image:
                sm_train_image = f"683313688378.dkr.ecr.{self.region}.amazonaws.com/sagemaker-xgboost:1.5-1"

            ct_cron = self.node.try_get_context("ct_schedule_cron") or ""

            ModelRegistry(self, "ModelRegistry", group_name=sm_pkg_group_name)

            source_stage = cicd.pipeline.stages[0]
            source_output = source_stage.actions[0].action_properties.outputs[0]

            SageMakerCiCd(
                self, "SmCiCd",
                artifacts_bucket=storage.artifacts_bucket,
                data_bucket=storage.data_bucket,
                codebuild_role=iam.codebuild_role,
                pipeline=cicd.pipeline,
                source_output=source_output,
                pkg_group_name=sm_pkg_group_name,
                train_image_uri=sm_train_image,
                sm_exec_role_arn=sm_exec.role.role_arn,
                sm_instance_type=sm_instance_type,
                endpoint_name=sm_endpoint_name,
                ct_schedule_cron=ct_cron,
            )

            iam.codebuild_role.add_to_policy(iam_cdk.PolicyStatement(
                sid="ReadSageMakerTrainingLogs",
                actions=[
                    "logs:DescribeLogStreams",
                    "logs:GetLogEvents",
                    "logs:FilterLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/sagemaker/*",
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/sagemaker/*:log-stream:*",
                ],
            ))
            iam.codebuild_role.add_to_policy(iam_cdk.PolicyStatement(
                actions=["logs:DescribeLogGroups"],
                resources=["*"],
            ))
            iam.codebuild_role.add_to_policy(iam_cdk.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[sm_exec.role.role_arn],
            ))

            CfnOutput(self, "SmPackageGroup", value=sm_pkg_group_name)
            CfnOutput(self, "SmEndpointName", value=sm_endpoint_name)

        CfnOutput(self, "ArtifactsBucket", value=storage.artifacts_bucket.bucket_name)
        CfnOutput(self, "DataBucket", value=storage.data_bucket.bucket_name)
        CfnOutput(self, "LogsBucket", value=storage.logs_bucket.bucket_name)
        CfnOutput(self, "EcrRepoUri", value=ecr.repo.repository_uri)
        if vpc:
            CfnOutput(self, "VpcId", value=vpc.vpc_id)

        enable_studio = bool(self.node.try_get_context("enable_studio") or False)
        if enable_studio and vpc:
            studio_domain_name = f"{cfg.project_name}-{cfg.env_name}-studio"
            studio_user = self.node.try_get_context("studio_user") or "admin"
            Studio(
                self,
                "Studio",
                vpc=vpc,
                kms_key=kms.key,
                domain_name=studio_domain_name,
                user_name=studio_user,
                s3_access_buckets=[storage.data_bucket, storage.artifacts_bucket],
            )
