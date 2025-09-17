from constructs import Construct
from aws_cdk import (
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_kms as kms,
    aws_sagemaker as sagemaker,
    CfnOutput,
)


class Studio(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        vpc: ec2.IVpc,
        kms_key: kms.IKey,
        domain_name: str,
        user_name: str,
        s3_access_buckets: list,
    ) -> None:
        super().__init__(scope, id)

        exec_role = iam.Role(
            self,
            "StudioExecRole",
            assumed_by=iam.ServicePrincipal("sagemaker.amazonaws.com"),
            description="SageMaker Studio execution role",
        )
        exec_role.add_managed_policy(iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSageMakerFullAccess"))

        for b in s3_access_buckets:
            b.grant_read_write(exec_role)
        kms_key.grant_encrypt_decrypt(exec_role)

        subnets = [s.subnet_id for s in vpc.private_subnets]

        domain = sagemaker.CfnDomain(
            self,
            "Domain",
            auth_mode="IAM",
            domain_name=domain_name,
            vpc_id=vpc.vpc_id,
            subnet_ids=subnets,
            app_network_access_type="VpcOnly",
            kms_key_id=kms_key.key_arn,
            default_user_settings=sagemaker.CfnDomain.UserSettingsProperty(
                execution_role=exec_role.role_arn
            ),
        )

        user = sagemaker.CfnUserProfile(
            self,
            "User",
            domain_id=domain.attr_domain_id,
            user_profile_name=user_name,
            user_settings=sagemaker.CfnUserProfile.UserSettingsProperty(
                execution_role=exec_role.role_arn
            ),
        )

        user.add_dependency(domain)

        CfnOutput(self, "StudioDomainId", value=domain.attr_domain_id)
        CfnOutput(self, "StudioUserProfile", value=user_name)
        CfnOutput(self, "StudioUrl",
                  value=f"https://{scope.region}.console.aws.amazon.com/sagemaker/home?region={scope.region}#/studio/launch?domainId={domain.attr_domain_id}&userProfile={user_name}")
