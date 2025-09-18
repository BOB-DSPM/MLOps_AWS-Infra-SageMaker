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
        shared_buckets: dict = None,  # 공유 버킷 설정
    ) -> None:
        super().__init__(scope, construct_id)
        stack = Stack.of(self)
        use_existing = bool(stack.node.try_get_context("use_existing_buckets") or False)
        existing_logs = stack.node.try_get_context("existing_logs_bucket_name")
        existing_artifacts = stack.node.try_get_context("existing_artifacts_bucket_name")
        existing_data = stack.node.try_get_context("existing_data_bucket_name")

        # 공유 버킷 설정이 있으면 사용
        if shared_buckets and "prod_data_bucket" in shared_buckets:
            existing_data = shared_buckets["prod_data_bucket"]
            use_existing = True

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


class StorageStack(Construct):
    """스토리지 스택 - BaseStorage 래퍼"""
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        name_prefix: str,
        shared_buckets: dict = None,
    ) -> None:
        super().__init__(scope, construct_id)
        
        # KMS 키는 부모 스택에서 가져와야 하므로 임시로 None 처리
        # 실제로는 DevMLOpsStack에서 KMS 키를 전달받아야 함
        from infra.kms_key import KMSStack
        
        # 프로젝트명과 환경명 파싱
        parts = name_prefix.split('-')
        project = parts[0] if len(parts) > 0 else "project"
        env = parts[1] if len(parts) > 1 else "dev"
        
        # 임시 KMS 키 생성 (실제로는 외부에서 전달받아야 함)
        temp_kms = KMSStack(self, "TempKms", name_prefix=name_prefix)
        
        self.base_storage = BaseStorage(
            self, "BaseStorage",
            project=project,
            env=env,
            kms_key=temp_kms.key,
            shared_buckets=shared_buckets
        )
        
        # 속성 노출
        self.data_bucket = self.base_storage.data_bucket
        self.artifacts_bucket = self.base_storage.artifacts_bucket
        self.logs_bucket = self.base_storage.logs_bucket