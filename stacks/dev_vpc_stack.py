from constructs import Construct
from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
)


class DevVPCStack(Stack):
    """개발 환경용 VPC 스택"""
    
    def __init__(self, scope: Construct, construct_id: str, cfg, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # 개발용 VPC 생성 (운영망과 다른 CIDR)
        self.dev_vpc = ec2.Vpc(
            self, "DevVPC",
            ip_addresses=ec2.IpAddresses.cidr("10.2.0.0/16"),  # 운영: 10.0.0.0/16, 추론: 10.1.0.0/16
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="DevPublic",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="DevPrivate", 
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )
        
        # VPC 엔드포인트 생성 - AWS 서비스에 프라이빗 접근
        self._create_vpc_endpoints()
        
        # 개발용 보안 그룹
        self.dev_security_group = ec2.SecurityGroup(
            self, "DevSecurityGroup",
            vpc=self.dev_vpc,
            description="Development environment security group",
            allow_all_outbound=True
        )
        
        # 내부 통신 허용
        self.dev_security_group.add_ingress_rule(
            peer=self.dev_security_group,
            connection=ec2.Port.all_traffic(),
            description="Allow all traffic within dev security group"
        )
        
        # 출력값
        CfnOutput(
            self, "DevVpcId",
            value=self.dev_vpc.vpc_id,
            description="Development VPC ID"
        )
        
        CfnOutput(
            self, "DevVpcCidr", 
            value=self.dev_vpc.vpc_cidr_block,
            description="Development VPC CIDR Block"
        )
        
        CfnOutput(
            self, "DevSecurityGroupId",
            value=self.dev_security_group.security_group_id,
            description="Development Security Group ID"
        )

    def _create_vpc_endpoints(self):
        """AWS 서비스 접근을 위한 VPC 엔드포인트 생성"""
        
        # SageMaker API VPC Endpoint
        self.dev_vpc.add_interface_endpoint(
            "DevSageMakerApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_API,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # SageMaker Runtime VPC Endpoint  
        self.dev_vpc.add_interface_endpoint(
            "DevSageMakerRuntimeEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_RUNTIME,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # SageMaker Feature Store Runtime VPC Endpoint
        self.dev_vpc.add_interface_endpoint(
            "DevSageMakerFeatureStoreEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_FEATURESTORE_RUNTIME,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # Athena VPC Endpoint
        self.dev_vpc.add_interface_endpoint(
            "DevAthenaEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ATHENA,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # Glue VPC Endpoint (Data Catalog용)
        self.dev_vpc.add_interface_endpoint(
            "DevGlueEndpoint", 
            service=ec2.InterfaceVpcEndpointAwsService.GLUE,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # S3 Gateway Endpoint (성능 향상 및 비용 절약)
        self.dev_vpc.add_gateway_endpoint(
            "DevS3GatewayEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)]
        )

        # ECR API VPC Endpoint (Docker 이미지 다운로드용)
        self.dev_vpc.add_interface_endpoint(
            "DevEcrApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # ECR Docker VPC Endpoint
        self.dev_vpc.add_interface_endpoint(
            "DevEcrDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # CloudWatch Logs VPC Endpoint
        self.dev_vpc.add_interface_endpoint(
            "DevCloudWatchLogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )
