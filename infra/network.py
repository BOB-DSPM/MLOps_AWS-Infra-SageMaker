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