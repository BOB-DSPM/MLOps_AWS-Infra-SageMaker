from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput
)
from infra.config import Config
from infra.network import BaseNetwork
from infra.kms_key import BaseKms
from infra.storage import BaseStorage
from infra.ecr_repo import BaseEcr
from infra.iam_role import CiCdIam
from infra.cicd import CiCdPipeline

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

        name_prefix = f"{cfg.project_name}={cfg.env_name}".lower()

        vpc = None
        if cfg.include_vpc:
            net = BaseNetwork(self, "Net")
            vpc = net.vpc
        
        kms = BaseKms(self, "Kms", alias=f"alias/{name_prefix}-s3")

        storage = BaseStorage(self, "Storage",
                              project = cfg.project_name, 
                              env = cfg.env_name, 
                              kms_key = kms.key, 
                              artifact_lifecycle_days = cfg.artifact_bucket_lifecycle_days)
        
        ecr = BaseEcr(self, "Ecr",
                      name = f"{cfg.project_name}-{cfg.env_name}".lower(),
                      keep_untagged = cfg.ecr_untagged_keep)
        
        iam = CiCdIam(self, "CiCdIam",
                      artifacts_bucket_arn = storage.artifacts_bucket.bucket_arn,
                      data_bucket_arn = storage.data_bucket.bucket_arn,
                      kms_key_arn = kms.key.key_arn,
                      ecr_repo_arn = ecr.repo.repository_arn)
                      
        if cfg.enable_pipeline:
            cicd = CiCdPipeline(self, "CiCd",
                                repo_name = cfg.codecommit_repo_name,
                                branch = cfg.pipeline_branch,
                                artifacts_bucket = storage.artifacts_bucket,
                                codebuild_role = iam.codebuild_role,
                                pipeline_role = iam.pipeline_role)
            CfnOutput(self, "CodeCommitCloneUrlHttp", value = cicd.repo.repository_clone_url_http)
            CfnOutput(self, "PipelineName", value = cicd.pipeline.pipeline_name)
        
        CfnOutput(self, "ArtifactsBucket", value = storage.artifacts_bucket.bucket_name)
        CfnOutput(self, "DateBucket", value = storage.data_bucket.bucket_name)
        CfnOutput(self, "LogsBucket", value = storage.logs_bucket.bucket_name)
        CfnOutput(self, "EcrRepoUri", value = ecr.repo.repository_uri)
        if vpc:
            CfnOutput(self, "VpcId", value = vpc.vpc_id)