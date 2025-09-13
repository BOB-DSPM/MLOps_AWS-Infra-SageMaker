from constructs import Construct
from aws_cdk import (
    Stack,
    aws_iam as iam,
)

class CiCdIam(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        artifacts_bucket_arn: str,
        data_bucket_arn: str,
        kms_key_arn: str,
        ecr_repo_arn: str,   
    ) -> None:
        super().__init__(scope, construct_id)

        parent = Stack.of(self)

        self.codebuild_role = iam.Role(
            parent, "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            description="Role for CodeBuild to build/push images and access S3/KMS",
        )
        self.codebuild_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryPowerUser")
        )
        self.codebuild_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=[
                artifacts_bucket_arn, f"{artifacts_bucket_arn}/*",
                data_bucket_arn, f"{data_bucket_arn}/*",
            ],
        ))
        self.codebuild_role.add_to_policy(iam.PolicyStatement(
            actions=["kms:Encrypt", "kms:Decrypt", "kms:DescribeKey", "kms:GenerateDataKey*"],
            resources=[kms_key_arn],
        ))
        self.codebuild_role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability", "ecr:CompleteLayerUpload",
                "ecr:UploadLayerPart", "ecr:InitiateLayerUpload",
                "ecr:PutImage", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
                "ecr:DescribeRepositories",
            ],
            resources=["*"],
        ))

        self.pipeline_role = iam.Role(
            parent, "CodePipelineRole",
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
            description="Role for CodePipeline to orchestrate stages and access artifact store",
        )
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=["*"],
        ))
        self.pipeline_role.add_to_policy(iam.PolicyStatement(
            actions=["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey*", "kms:DescribeKey"],
            resources=[kms_key_arn],
        ))