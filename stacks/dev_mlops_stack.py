from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput,
    aws_iam as iam_cdk,
    aws_ec2 as ec2,
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
from infra.feature_store import FeatureGroup, UserInteractionFeatureGroup
from infra.studio import Studio

## hjahahahahahaahahah
def _sanitize_alias_component(s: str) -> str:
    """KMS Alias 허용문자(a-zA-Z0-9:/_-) 외 문자는 '-'로 치환"""
    import re
    return re.sub(r"[^a-zA-Z0-9:/_-]", "-", s)


class DevMLOpsStack(Stack):
    """개발 환경용 MLOps 스택 - 운영망 완전 복사본 (이름만 변경)"""
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        cfg: Config,
        dev_vpc_id: str,  # 개발용 VPC ID 받아오기
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 개발 환경 전용 네이밍 (운영망과 충돌 방지)
        name_prefix = f"{cfg.project_name}-dev-{cfg.env_name}".lower()
        alias_name = f"alias/{_sanitize_alias_component(name_prefix)}-s3"

        # 기존 개발용 VPC 가져오기
        vpc = ec2.Vpc.from_lookup(self, "DevVpc", vpc_id=dev_vpc_id)

        # ========================================
        # KMS 키 (개발 전용)
        # ========================================
        kms = BaseKms(self, "DevKms", alias=alias_name)

        # ========================================
        # 스토리지 (개발 전용)
        # ========================================
        storage = BaseStorage(
            self, "DevStorage",
            project=f"{cfg.project_name}-dev",  # 개발 전용 프로젝트명
            env=cfg.env_name,
            kms_key=kms.key,
            artifact_lifecycle_days=cfg.artifact_bucket_lifecycle_days,
        )

        # ========================================
        # ECR 리포지토리 (개발 전용)
        # ========================================
        ecr = BaseEcr(
            self, "DevEcr",
            name=f"{cfg.project_name}-dev-{cfg.env_name}".lower(),
            keep_untagged=cfg.ecr_untagged_keep,
        )

        # ========================================
        # IAM 역할 (개발 전용)
        # ========================================
        iam = CiCdIam(
            self, "DevCiCdIam",
            artifacts_bucket_arn=storage.artifacts_bucket.bucket_arn,
            data_bucket_arn=storage.data_bucket.bucket_arn,
            kms_key_arn=kms.key.key_arn,
            ecr_repo_arn=ecr.repo.repository_arn,
        )

        # ========================================
        # CI/CD 파이프라인 (개발 전용)
        # ========================================
        cicd = None
        if cfg.enable_pipeline:
            cicd = CiCdPipeline(
                self, "DevCiCd",
                repo_name=f"{cfg.codecommit_repo_name}-dev",  # 개발 전용 리포
                branch=cfg.pipeline_branch,
                artifacts_bucket=storage.artifacts_bucket,
                codebuild_role=iam.codebuild_role,
                pipeline_role=iam.pipeline_role,
            )
            CfnOutput(self, "DevCodeCommitCloneUrlHttp", value=cicd.repo.repository_clone_url_http)
            CfnOutput(self, "DevPipelineName", value=cicd.pipeline.pipeline_name)

        # ========================================
        # SageMaker 실행 역할 (개발 전용)
        # ========================================
        sm_exec = SmExecutionRole(
            self, "DevSmExecRole",
            data_bucket=storage.data_bucket,
            artifacts_bucket=storage.artifacts_bucket,
            kms_key=kms.key,
        )

        # S3 버킷 정책 설정 (운영망과 동일)
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

        # ========================================
        # Feature Store (개발 전용)
        # ========================================
        enable_feature_group = True  # 개발망에서는 활성화
        use_existing_feature_group = False
        feature_group_name = f"{name_prefix}-feature-group-v2"

        if enable_feature_group and not use_existing_feature_group:
            fg = FeatureGroup(
                self,
                "DevFeatureGroup",
                feature_group_name=feature_group_name,
                s3_uri=f"s3://{storage.data_bucket.bucket_name}/feature-store/",
                role=sm_exec.role,
                kms_key_arn=kms.key.key_arn,
                record_identifier_name="id",
                event_time_name="event_time",
            )

            if storage.data_bucket.policy:
                fg.feature_group.node.add_dependency(storage.data_bucket.policy)
                
            self.feature_group_name = feature_group_name
        else:
            self.feature_group_name = f"{name_prefix}-feature-group-ctr"

        # 사용자 상호작용 데이터용 Feature Group (개발 전용)
        user_interaction_fg = UserInteractionFeatureGroup(
            self,
            "DevUserInteractionFeatureGroup",
            feature_group_name=f"{name_prefix}-user-interactions-v1",
            s3_uri=f"s3://{storage.data_bucket.bucket_name}/feature-store/user-interactions/",
            role=sm_exec.role,
            kms_key_arn=kms.key.key_arn,
            record_identifier_name="interaction_id",
            event_time_name="event_time",
        )

        if storage.data_bucket.policy:
            user_interaction_fg.feature_group.node.add_dependency(storage.data_bucket.policy)
            
        self.user_interaction_fg_name = f"{name_prefix}-user-interactions-v1"

        # ========================================
        # SageMaker CI/CD (개발 전용 MLOps 파이프라인)
        # ========================================
        enable_sm_ci = True  # 개발망에서는 기본 활성화
        if enable_sm_ci and cicd is not None:
            sm_pkg_group_name = f"{name_prefix}-pkg"
            sm_endpoint_name = f"{name_prefix}-endpoint"
            sm_instance_type = "ml.m5.large"
            sm_train_image = f"366743142698.dkr.ecr.{self.region}.amazonaws.com/sagemaker-xgboost:1.7-1"
            ct_cron = ""

            ModelRegistry(self, "DevModelRegistry", group_name=sm_pkg_group_name)

            source_stage = cicd.pipeline.stages[0]
            source_output = source_stage.actions[0].action_properties.outputs[0]

            SageMakerCiCd(
                self, "DevSmCiCd",
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
                use_sm_pipeline=True,  # SageMaker Pipeline 사용
                use_feature_store=True,
                feature_group_name=self.feature_group_name,
            )

            # 추가 IAM 권한 (운영망과 동일)
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

            CfnOutput(self, "DevSmPackageGroup", value=sm_pkg_group_name)
            CfnOutput(self, "DevSmEndpointName", value=sm_endpoint_name)

        # ========================================
        # 출력값들 (개발 전용)
        # ========================================
        CfnOutput(self, "DevArtifactsBucket", value=storage.artifacts_bucket.bucket_name)
        CfnOutput(self, "DevDataBucket", value=storage.data_bucket.bucket_name)
        CfnOutput(self, "DevLogsBucket", value=storage.logs_bucket.bucket_name)
        CfnOutput(self, "DevEcrRepoUri", value=ecr.repo.repository_uri)
        CfnOutput(self, "DevSmExecRoleArn", value=sm_exec.role.role_arn)
        if vpc:
            CfnOutput(self, "DevVpcId", value=vpc.vpc_id)

        # SageMaker Studio (개발 전용)
        enable_studio = True
        if enable_studio and vpc:
            studio_domain_name = f"{cfg.project_name}-dev-{cfg.env_name}-studio"
            studio_user = "dev-admin"
            Studio(
                self,
                "DevStudio",
                vpc=vpc,
                kms_key=kms.key,
                domain_name=studio_domain_name,
                user_name=studio_user,
                s3_access_buckets=[storage.data_bucket, storage.artifacts_bucket],
            )

        # 다른 스택에서 참조할 수 있도록 속성 노출
        self.data_bucket = storage.data_bucket
        self.artifacts_bucket = storage.artifacts_bucket
        self.vpc = vpc
