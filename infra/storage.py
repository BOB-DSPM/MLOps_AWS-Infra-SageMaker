from constructs import Construct
from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    RemovalPolicy,
    Duration,
    Stack,
)

def _enforce_ssl(bucket: s3.Bucket):
    bucket.add_to_resource_policy(
        iam.PolicyStatement(
            sid="HttpsOnlyBucket",
            effect=iam.Effect.DENY,
            principals=[iam.AnyPrincipal()],
            actions=["s3:*"],
            resources=[bucket.bucket_arn],
            conditions={"Bool": {"aws:SecureTransport": "false"}},
        )
    )
    bucket.add_to_resource_policy(
        iam.PolicyStatement(
            sid="HttpsOnlyObjects",
            effect=iam.Effect.DENY,
            principals=[iam.AnyPrincipal()],
            actions=["s3:*"],
            resources=[bucket.arn_for_objects("*")],
            conditions={"Bool": {"aws:SecureTransport": "false"}},
        )
    )

class BaseStorage(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        project: str,
        env: str,
        kms_key,
        artifact_lifecycle_days: int = 90,
    ) -> None:
        super().__init__(scope, construct_id)
        stack = Stack.of(self)
        use_existing = bool(stack.node.try_get_context("use_existing_buckets") or False)
        existing_logs = stack.node.try_get_context("existing_logs_bucket_name")
        existing_artifacts = stack.node.try_get_context("existing_artifacts_bucket_name")
        existing_data = stack.node.try_get_context("existing_data_bucket_name")

        logs_bucket_name = f"{project}-{env}-logs".lower()
        if use_existing and existing_logs:
            self.logs_bucket = s3.Bucket.from_bucket_name(self, "LogsBucket", existing_logs)
        else:
            self.logs_bucket = s3.Bucket(
                self,
                "LogsBucket",
                bucket_name=logs_bucket_name,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                encryption=s3.BucketEncryption.S3_MANAGED,
                enforce_ssl=True,
                versioned=True,
                lifecycle_rules=[
                    s3.LifecycleRule(
                        enabled=True,
                        expiration=Duration.days(365),
                        noncurrent_version_expiration=Duration.days(180),
                    )
                ],
                removal_policy=RemovalPolicy.RETAIN,
            )
            _enforce_ssl(self.logs_bucket)

        artifacts_bucket_name = f"{project}-{env}-artifacts".lower()
        if use_existing and existing_artifacts:
            self.artifacts_bucket = s3.Bucket.from_bucket_name(self, "ArtifactsBucket", existing_artifacts)
        else:
            self.artifacts_bucket = s3.Bucket(
                self,
                "ArtifactsBucket",
                bucket_name=artifacts_bucket_name,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                encryption=s3.BucketEncryption.KMS,
                encryption_key=kms_key,
                enforce_ssl=True,
                versioned=True,
                server_access_logs_bucket=self.logs_bucket,
                server_access_logs_prefix="artifacts/",
                lifecycle_rules=[
                    s3.LifecycleRule(
                        enabled=True,
                        expiration=Duration.days(artifact_lifecycle_days),
                        noncurrent_version_expiration=Duration.days(artifact_lifecycle_days),
                    )
                ],
                removal_policy=RemovalPolicy.RETAIN,
            )
            _enforce_ssl(self.artifacts_bucket)

        data_bucket_name = f"{project}-{env}-data".lower()
        if use_existing and existing_data:
            self.data_bucket = s3.Bucket.from_bucket_name(self, "DataBucket", existing_data)
        else:
            self.data_bucket = s3.Bucket(
                self,
                "DataBucket",
                bucket_name=data_bucket_name,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                encryption=s3.BucketEncryption.KMS,
                encryption_key=kms_key,
                enforce_ssl=True,
                versioned=True,
                server_access_logs_bucket=self.logs_bucket,
                server_access_logs_prefix="data/",  
                removal_policy=RemovalPolicy.RETAIN,
            )
            _enforce_ssl(self.data_bucket)