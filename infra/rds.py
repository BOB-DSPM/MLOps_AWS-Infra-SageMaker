from constructs import Construct
from aws_cdk import (
    aws_rds as rds,
    aws_ec2 as ec2,
    aws_secretsmanager as secretsmanager,
    aws_iam as iam,
    RemovalPolicy,
    Duration,
)

class RdsConstruct(Construct):
    """Feature Store와 연동할 RDS 데이터베이스"""
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        database_name: str = "mlopsdb",
        username: str = "mlopsuser",
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # DB 서브넷 그룹 생성
        self.db_subnet_group = rds.SubnetGroup(
            self, "DbSubnetGroup",
            description="Subnet group for MLOps RDS database",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # RDS 보안 그룹
        self.security_group = ec2.SecurityGroup(
            self, "RdsSecurityGroup",
            vpc=vpc,
            description="Security group for MLOps RDS database",
            allow_all_outbound=False
        )
        
        # PostgreSQL 포트 (5432) 인바운드 허용
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(5432),
            description="Allow PostgreSQL connections from VPC"
        )
        
        # 데이터베이스 자격 증명 생성
        self.db_credentials = secretsmanager.Secret(
            self, "DbCredentials",
            description="RDS database credentials for MLOps",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "' + username + '"}',
                generate_string_key="password",
                exclude_characters=' %+~`#$&*()|[]{}:;<>?!\'/@"\\',
                password_length=32
            ),
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Aurora Serverless v2 클러스터 생성 (가장 저렴한 옵션)
        self.database_cluster = rds.DatabaseCluster(
            self, "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_7
            ),
            credentials=rds.Credentials.from_secret(self.db_credentials),
            default_database_name=database_name,
            vpc=vpc,
            subnet_group=self.db_subnet_group,
            security_groups=[self.security_group],
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
            serverless_v2_min_capacity=0.5,  # 최소 ACU (가장 저렴)
            serverless_v2_max_capacity=1.0,  # 최대 ACU 제한
            writer=rds.ClusterInstance.serverless_v2("writer", 
                instance_identifier="aurora-writer"
            )
        )
        
        # Lambda/Glue용 보안 그룹 (RDS 접근용)
        self.lambda_security_group = ec2.SecurityGroup(
            self, "LambdaRdsSecurityGroup",
            vpc=vpc,
            description="Security group for Lambda functions accessing RDS",
            allow_all_outbound=True
        )
        
        # Lambda → RDS 접근 허용
        self.security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.lambda_security_group.security_group_id),
            connection=ec2.Port.tcp(5432),
            description="Allow Lambda functions to access RDS"
        )
    
    def grant_connect(self, grantee: iam.IGrantable):
        """RDS 연결 권한 부여"""
        grantee.grant_principal.add_to_policy(iam.PolicyStatement(
            actions=[
                "rds:DescribeDBInstances",
                "rds:DescribeDBClusters", 
                "rds-db:connect",
            ],
            resources=[self.database_cluster.cluster_arn]
        ))
    
    def grant_secret_read(self, grantee: iam.IGrantable):
        """DB 자격 증명 읽기 권한 부여"""
        return self.db_credentials.grant_read(grantee)

    @property
    def connection_string(self) -> str:
        """RDS 연결 문자열 반환"""
        return f"postgresql://{self.database_cluster.cluster_endpoint.hostname}:{self.database_cluster.cluster_endpoint.port}/{self.database_cluster.cluster_identifier}"
    
    @property
    def endpoint(self) -> str:
        """RDS 엔드포인트 반환"""
        return self.database_cluster.cluster_endpoint.hostname
    
    @property  
    def port(self) -> int:
        """RDS 포트 반환"""
        return self.database_cluster.cluster_endpoint.port