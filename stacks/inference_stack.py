from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
)


class ModelInferenceStack(Stack):
    """모델 추론을 위한 별도 VPC와 웹 애플리케이션 스택"""
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        sagemaker_endpoint_name: str,
        model_package_group_name: str,
        user_interaction_fg_name: str,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 새로운 VPC 생성 (MLOps VPC와 분리)
        self.vpc = ec2.Vpc(
            self, "InferenceVpc",
            max_azs=2,
            ip_addresses=ec2.IpAddresses.cidr("10.1.0.0/16"),  # MLOps VPC와 다른 CIDR
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet", 
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # ECS 클러스터 생성
        cluster = ecs.Cluster(
            self, "InferenceCluster",
            vpc=self.vpc,
            container_insights=True,
        )

        # 모델 추론용 태스크 역할
        task_role = iam.Role(
            self, "InferenceTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Role for inference web app to call SageMaker endpoint",
        )

        # SageMaker 엔드포인트 호출 권한
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:InvokeEndpoint",
                    "sagemaker:DescribeEndpoint",
                ],
                resources=[
                    f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/{sagemaker_endpoint_name}"
                ],
            )
        )

        # 모델 패키지 조회 권한 (모델 정보 확인용)
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:ListModelPackages",
                    "sagemaker:DescribeModelPackage",
                ],
                resources=[
                    f"arn:aws:sagemaker:{self.region}:{self.account}:model-package-group/{model_package_group_name}",
                    f"arn:aws:sagemaker:{self.region}:{self.account}:model-package-group/{model_package_group_name}/*",
                ],
            )
        )

        # Feature Store 권한 추가
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:PutRecord",
                    "sagemaker:GetRecord",
                    "sagemaker:DescribeFeatureGroup",
                ],
                resources=[
                    f"arn:aws:sagemaker:{self.region}:{self.account}:feature-group/{user_interaction_fg_name}",
                ],
            )
        )

        # CloudWatch 로그 그룹
        log_group = logs.LogGroup(
            self, "InferenceAppLogs",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        # Fargate 서비스 생성
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, "InferenceService",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    directory="./inference_app",
                ),
                container_port=8080,
                environment={
                    "SAGEMAKER_ENDPOINT_NAME": sagemaker_endpoint_name,
                    "MODEL_PACKAGE_GROUP": model_package_group_name,
                    "USER_INTERACTION_FG_NAME": user_interaction_fg_name,
                    "AWS_DEFAULT_REGION": self.region,
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="inference-app",
                    log_group=log_group,
                ),
                task_role=task_role,
            ),
            public_load_balancer=True,
            listener_port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
        )

        # 헬스체크 설정
        fargate_service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
        )

        # Auto Scaling 설정
        scalable_target = fargate_service.service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=5,
        )

        scalable_target.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
        )

        scalable_target.scale_on_memory_utilization(
            "MemoryScaling", 
            target_utilization_percent=80,
        )

        # Outputs
        CfnOutput(
            self, "InferenceVpcId",
            value=self.vpc.vpc_id,
            description="VPC ID for inference application"
        )
        
        CfnOutput(
            self, "LoadBalancerUrl",
            value=f"http://{fargate_service.load_balancer.load_balancer_dns_name}",
            description="URL to access the inference web application"
        )
        
        CfnOutput(
            self, "EcsClusterName",
            value=cluster.cluster_name,
            description="ECS cluster name for inference service"
        )

        # 속성으로 저장 (다른 스택에서 참조 가능)
        self.load_balancer_url = fargate_service.load_balancer.load_balancer_dns_name
        self.cluster = cluster
        self.service = fargate_service.service
