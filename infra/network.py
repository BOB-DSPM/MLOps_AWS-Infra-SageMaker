from constructs import Construct
from aws_cdk import (
    aws_ec2 as ec2,
)

class BaseNetwork(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, cidr="10.20.0.0/16") -> None:
        super().__init__(scope, construct_id)

        self.vpc = ec2.Vpc(
            self, "Vpc",
            ip_addresses = ec2.IpAddresses.cidr(cidr),
            max_azs = 2,
            nat_gateways = 1,
            subnet_configuration = [
                ec2.SubnetConfiguration(
                    name = "poublic",
                    subnet_type = ec2.SubnetType.PUBLIC,
                    cidr_mask = 24),
                ec2.SubnetConfiguration(
                        name = "private",
                        subnet_type = ec2.SubnetType.PRIVATE_WITH_EGRESS,
                        cidr_mask = 20),
            ]
        )

        # VPC Endpoints for AWS Services Access
        self._create_vpc_endpoints()

    def _create_vpc_endpoints(self):
        """Create VPC endpoints for AWS services to enable private access"""
        
        # SageMaker API VPC Endpoint
        self.vpc.add_interface_endpoint(
            "SageMakerApiEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_API,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # SageMaker Runtime VPC Endpoint  
        self.vpc.add_interface_endpoint(
            "SageMakerRuntimeEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_RUNTIME,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # SageMaker Feature Store Runtime VPC Endpoint
        self.vpc.add_interface_endpoint(
            "SageMakerFeatureStoreEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SAGEMAKER_FEATURESTORE_RUNTIME,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # Athena VPC Endpoint
        self.vpc.add_interface_endpoint(
            "AthenaEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ATHENA,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # Glue VPC Endpoint (for Data Catalog)
        self.vpc.add_interface_endpoint(
            "GlueEndpoint", 
            service=ec2.InterfaceVpcEndpointAwsService.GLUE,
            subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        )

        # S3 Gateway Endpoint (for better performance and no charges)
        self.vpc.add_gateway_endpoint(
            "S3GatewayEndpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)]
        )