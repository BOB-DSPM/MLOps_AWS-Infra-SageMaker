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

        self.role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFeatureStoreAccess")
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

        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                "s3:GetBucketAcl",
                "s3:GetBucketLocation",
                "s3:ListBucket",
                "s3:GetObject",
                "s3:PutObject",
                "s3:PutObjectAcl",
            ],
            resources=[
                data_bucket.bucket_arn,
                f"{data_bucket.bucket_arn}/*"
            ],
        ))

        # Allow decrypt on any KMS key (buckets may be pre-existing with different keys)
        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey",
            ],
            resources=["*"],
        ))

        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                "glue:GetDatabase",
                "glue:GetDatabases",
                "glue:GetTable",
                "glue:GetTables",
                "glue:GetPartition",
                "glue:GetPartitions",
                "athena:StartQueryExecution",
                "athena:GetQueryExecution",
                "athena:GetQueryResults",
                "athena:StopQueryExecution",
                "athena:ListWorkGroups",
                "athena:GetWorkGroup",
            ],
            resources=["*"],
        ))

        # Allow SageMaker Pipelines to tag Processing/Training jobs created with this role
        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                "sagemaker:AddTags",
                "sagemaker:TagResource",
                "sagemaker:UntagResource",
                "sagemaker:ListTags",
            ],
            resources=["*"]
        ))

        # Read Feature Store metadata (used to resolve offline store Data Catalog)
        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                "sagemaker:DescribeFeatureGroup",
                "sagemaker:ListFeatureGroups",
                "sagemaker:DescribeFeatureMetadata",
                "sagemaker:ListFeatureMetadata",
            ],
            resources=["*"]
        ))

        # Allow this role (used as the SageMaker Pipeline service role) to create jobs and register models
        self.role.add_to_policy(iam.PolicyStatement(
            actions=[
                # Processing/Training
                "sagemaker:CreateProcessingJob",
                "sagemaker:DescribeProcessingJob",
                "sagemaker:StopProcessingJob",
                "sagemaker:CreateTrainingJob",
                "sagemaker:DescribeTrainingJob",
                "sagemaker:StopTrainingJob",
                # Models & Model Registry used by RegisterModel step
                "sagemaker:CreateModel",
                "sagemaker:DescribeModel",
                "sagemaker:CreateModelPackage",
                "sagemaker:CreateModelPackageGroup",
                "sagemaker:DescribeModelPackageGroup",
                "sagemaker:DescribeModelPackage",
                "sagemaker:ListModelPackages",
                "sagemaker:UpdateModelPackage",
            ],
            resources=["*"]
        ))

        # The pipeline role must be able to pass the execution role to SageMaker jobs
        self.role.add_to_policy(iam.PolicyStatement(
            actions=["iam:PassRole"],
            resources=[self.role.role_arn],
        ))
