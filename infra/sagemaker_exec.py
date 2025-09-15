from constructs import Construct
from aws_cdk import (
    aws_iam as iam,
    aws_s3 as s3,
    aws_kms as kms,
)

class SmExecutionRole(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        data_bucket: s3.IBucket,
        artifacts_bucket: s3.IBucket,
        kms_key: kms.IKey,
    ) -> None:
        super().__init__(scope, construct_id)

        self.role = iam.Role(
            self, "Role",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            description="Execution role for SageMaker training/inference",
        )

        data_bucket.grant_read_write(self.role)
        artifacts_bucket.grant_read_write(self.role)
        kms_key.grant_encrypt_decrypt(self.role)

        self.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")
        )

        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ecr:GetAuthorizationToken",
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:DescribeImages",
            ],
            resources=["*"],
        ))

        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                "ecr-public:GetAuthorizationToken",
                "ecr-public:BatchCheckLayerAvailability",
                "ecr-public:GetDownloadUrlForLayer",
                "ecr-public:BatchGetImage",
            ],
            resources=["*"],
        ))
