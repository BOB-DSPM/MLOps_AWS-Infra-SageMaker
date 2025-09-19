from constructs import Construct
from aws_cdk import (
    Stack, CfnOutput, Duration,
    aws_iam as iam_cdk,
    aws_ec2 as ec2,
    aws_codebuild as codebuild,
    aws_codepipeline_actions as codepipeline_actions,
    aws_sns as sns,
)
from infra.config import Config
from infra.network import BaseNetwork
from infra.kms_key import BaseKms
from infra.storage import BaseStorage
from infra.ecr_repo import BaseEcr
from infra.iam_role import CiCdIam
from infra.cicd import CiCdPipeline
from infra.sagemaker_exec import SmExecutionRole
from infra.sagemaker_ci import ModelRegistry, SageMakerCiCd
from infra.feature_store import FeatureGroup, UserInteractionFeatureGroup
from infra.studio import Studio

## hjahahahahahaahahah
def _sanitize_alias_component(s: str) -> str:
    """KMS Alias 허용문자(a-zA-Z0-9:/_-) 외 문자는 '-'로 치환"""
    import re
    return re.sub(r"[^a-zA-Z0-9:/_-]", "-", s)


class DevMLOpsStack(Stack):
    """개발 환경용 MLOps 스택 - 운영망 완전 복사본 (이름만 변경)"""
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        cfg: Config,
        dev_vpc_id: str,  # 개발용 VPC ID 받아오기
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 개발 환경 전용 네이밍 (운영망과 충돌 방지)
        name_prefix = f"{cfg.project_name}-dev-{cfg.env_name}".lower()
        alias_name = f"alias/{_sanitize_alias_component(name_prefix)}-s3"

        # 기존 개발용 VPC 가져오기
        vpc = ec2.Vpc.from_lookup(self, "DevVpc", vpc_id=dev_vpc_id)

        # ========================================
        # KMS 키 (개발 전용)
        # ========================================
        kms = BaseKms(self, "DevKms", alias=alias_name)

        # ========================================
        # 스토리지 (개발 전용)
        # ========================================
        storage = BaseStorage(
            self, "DevStorage",
            project=f"{cfg.project_name}-dev",  # 개발 전용 프로젝트명
            env=cfg.env_name,
            kms_key=kms.key,
            artifact_lifecycle_days=cfg.artifact_bucket_lifecycle_days,
        )

        # ========================================
        # ECR 리포지토리 (개발 전용)
        # ========================================
        ecr = BaseEcr(
            self, "DevEcr",
            name=f"{cfg.project_name}-dev-{cfg.env_name}".lower(),
            keep_untagged=cfg.ecr_untagged_keep,
        )

        # ========================================
        # IAM 역할 (개발 전용)
        # ========================================
        iam = CiCdIam(
            self, "DevCiCdIam",
            artifacts_bucket_arn=storage.artifacts_bucket.bucket_arn,
            data_bucket_arn=storage.data_bucket.bucket_arn,
            kms_key_arn=kms.key.key_arn,
            ecr_repo_arn=ecr.repo.repository_arn,
        )

        # ========================================
        # CI/CD 파이프라인 (개발 전용)
        # ========================================
        cicd = None
        cross_repo_deploy = None  # 변수 초기화
        
        if cfg.enable_pipeline:
            cicd = CiCdPipeline(
                self, "DevCiCd",
                repo_name=f"{cfg.codecommit_repo_name}-dev",  # 개발 전용 리포
                branch=cfg.pipeline_branch,
                artifacts_bucket=storage.artifacts_bucket,
                codebuild_role=iam.codebuild_role,
                pipeline_role=iam.pipeline_role,
            )
            CfnOutput(self, "DevCodeCommitCloneUrlHttp", value=cicd.repo.repository_clone_url_http)
            CfnOutput(self, "DevPipelineName", value=cicd.pipeline.pipeline_name)

            # ========================================
            # Cross-repo 배포 기능 (개발 → 운영)
            # ========================================
            
            # SNS 토픽 생성 (배포 알림용)
            deployment_topic = sns.Topic(
                self, "DevToProdDeploymentTopic",
                topic_name=f"{name_prefix}-deployment-notifications",
                display_name="Dev to Prod Deployment Notifications"
            )

            # Cross-repo 배포용 IAM 역할
            cross_repo_role = iam_cdk.Role(
                self, "CrossRepoDeployRole",
                assumed_by=iam_cdk.ServicePrincipal("codebuild.amazonaws.com"),
                inline_policies={
                    "CrossRepoPolicy": iam_cdk.PolicyDocument(
                        statements=[
                            # 개발 레포 읽기
                            iam_cdk.PolicyStatement(
                                effect=iam_cdk.Effect.ALLOW,
                                actions=[
                                    "codecommit:GitPull",
                                    "codecommit:GitPush",
                                    "codecommit:GetBranch",
                                    "codecommit:GetCommit",
                                    "codecommit:GetRepository",
                                    "codecommit:ListBranches",
                                    "codecommit:ListRepositories"
                                ],
                                resources=[f"arn:aws:codecommit:{self.region}:{self.account}:{cfg.codecommit_repo_name}-dev"],
                            ),
                            # 운영 레포 쓰기
                            iam_cdk.PolicyStatement(
                                effect=iam_cdk.Effect.ALLOW,
                                actions=[
                                    "codecommit:GitPush",
                                    "codecommit:GitPull",
                                    "codecommit:GetBranch",
                                    "codecommit:GetCommit",
                                    "codecommit:GetRepository",
                                    "codecommit:PutFile",
                                    "codecommit:CreateCommit"
                                ],
                                resources=[f"arn:aws:codecommit:{self.region}:{self.account}:{cfg.codecommit_repo_name}"],
                            ),
                            # CodeBuild 기본 권한
                            iam_cdk.PolicyStatement(
                                effect=iam_cdk.Effect.ALLOW,
                                actions=[
                                    "logs:CreateLogGroup",
                                    "logs:CreateLogStream",
                                    "logs:PutLogEvents"
                                ],
                                resources=[f"arn:aws:logs:{self.region}:{self.account}:*"],
                            ),
                            # SNS 알림 권한
                            iam_cdk.PolicyStatement(
                                effect=iam_cdk.Effect.ALLOW,
                                actions=["sns:Publish"],
                                resources=[deployment_topic.topic_arn],
                            ),
                        ]
                    )
                },
            )

            # Cross-repo 배포 CodeBuild 프로젝트
            cross_repo_deploy = codebuild.Project(
                self, "CrossRepoDeployProject",
                project_name=f"{name_prefix}-cross-repo-deploy",
                environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                    privileged=False,
                    environment_variables={
                        "PROD_REPO_NAME": codebuild.BuildEnvironmentVariable(
                            value=cfg.codecommit_repo_name
                        ),
                        "AWS_REGION": codebuild.BuildEnvironmentVariable(
                            value=self.region
                        ),
                        "SNS_TOPIC_ARN": codebuild.BuildEnvironmentVariable(
                            value=deployment_topic.topic_arn
                        ),
                    }
                ),
                build_spec=codebuild.BuildSpec.from_object({
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "runtime-versions": {
                                "python": "3.11"
                            },
                            "commands": [
                                "echo Installing dependencies...",
                                "pip install git-remote-codecommit boto3",
                            ]
                        },
                        "pre_build": {
                            "commands": [
                                "echo Setting up git configuration...",
                                "git config --global user.email 'dev-pipeline@mlops.com'",
                                "git config --global user.name 'DevPipeline'",
                                "git config --global credential.helper '!aws codecommit credential-helper $@'",
                                "git config --global credential.UseHttpPath true",
                            ]
                        },
                        "build": {
                            "commands": [
                                "echo Starting deployment to production repository...",
                                "DEPLOYMENT_START_TIME=$(date '+%Y-%m-%d %H:%M:%S')",
                                
                                # 운영 레포 클론
                                "echo Cloning production repository...",
                                "git clone codecommit://$AWS_REGION/$PROD_REPO_NAME prod-repo",
                                "cd prod-repo",
                                "git checkout main || git checkout -b main",
                                
                                # 선택적 파일 복사
                                "echo Copying approved code from dev...",
                                "cp -r $CODEBUILD_SRC_DIR/pipelines . || echo 'pipelines directory not found'",
                                "cp -r $CODEBUILD_SRC_DIR/inference_app . || echo 'inference_app directory not found'",
                                "cp $CODEBUILD_SRC_DIR/requirements.txt . || echo 'requirements.txt not found'",
                                "cp $CODEBUILD_SRC_DIR/buildspec.yml . || echo 'buildspec.yml not found'",
                                "cp $CODEBUILD_SRC_DIR/*.py . || echo 'Python files not found'",
                                
                                # 커밋 및 푸시
                                "if [ -n \"$(git status --porcelain)\" ]; then",
                                "  git add .",
                                "  COMMIT_MSG=\"🚀 Auto deploy from dev: $DEPLOYMENT_START_TIME - Approved model\"",
                                "  git commit -m \"$COMMIT_MSG\"",
                                "  git push origin main",
                                "  DEPLOYMENT_STATUS='SUCCESS'",
                                "  echo '✅ Successfully deployed to production!'",
                                "else",
                                "  DEPLOYMENT_STATUS='NO_CHANGES'",
                                "  echo 'ℹ️ No changes to deploy'",
                                "fi",
                            ]
                        },
                        "post_build": {
                            "commands": [
                                "echo Sending deployment notification...",
                                "DEPLOYMENT_END_TIME=$(date '+%Y-%m-%d %H:%M:%S')",
                                
                                # SNS 알림 발송
                                "MESSAGE=\"🔄 Dev to Prod Deployment Report\\n\\n\"",
                                "MESSAGE=\"${MESSAGE}📅 Start Time: $DEPLOYMENT_START_TIME\\n\"",
                                "MESSAGE=\"${MESSAGE}📅 End Time: $DEPLOYMENT_END_TIME\\n\"",
                                "MESSAGE=\"${MESSAGE}📊 Status: $DEPLOYMENT_STATUS\\n\"",
                                "MESSAGE=\"${MESSAGE}🎯 Target Repo: $PROD_REPO_NAME\\n\"",
                                "MESSAGE=\"${MESSAGE}🔗 Production pipeline should be triggered automatically\"",
                                "aws sns publish --topic-arn $SNS_TOPIC_ARN --message \"$MESSAGE\" --subject 'MLOps Dev to Prod Deployment' --region $AWS_REGION",
                                
                                "echo 🎉 Deployment process completed!"
                            ]
                        }
                    }
                }),
                role=cross_repo_role,
                timeout=Duration.minutes(15),
            )

            # 출력값 추가
            CfnOutput(
                self, "CrossRepoDeployProjectName",
                value=cross_repo_deploy.project_name,
                description="CodeBuild project for dev to prod deployment"
            )

            CfnOutput(
                self, "DeploymentNotificationTopic",
                value=deployment_topic.topic_arn,
                description="SNS topic for deployment notifications"
            )

        # ========================================
        # SageMaker 실행 역할 (개발 전용)
        # ========================================
        sm_exec = SmExecutionRole(
            self, "DevSmExecRole",
            data_bucket=storage.data_bucket,
            artifacts_bucket=storage.artifacts_bucket,
            kms_key=kms.key,
        )

        # S3 버킷 정책 설정 (운영망과 동일)
        storage.data_bucket.add_to_resource_policy(iam_cdk.PolicyStatement(
            principals=[iam_cdk.ArnPrincipal(sm_exec.role.role_arn)],
            actions=[
                "s3:GetBucketAcl",
                "s3:GetBucketLocation",
                "s3:ListBucket",
            ],
            resources=[storage.data_bucket.bucket_arn],
        ))
        storage.data_bucket.add_to_resource_policy(iam_cdk.PolicyStatement(
            principals=[iam_cdk.ArnPrincipal(sm_exec.role.role_arn)],
            actions=[
                "s3:GetObject",
                "s3:PutObject",
                "s3:PutObjectAcl",
            ],
            resources=[storage.data_bucket.arn_for_objects("feature-store/*")],
        ))

        # 운영 Feature Store 접근 권한 추가
        sm_exec.role.add_to_policy(iam_cdk.PolicyStatement(
            actions=[
                "sagemaker:DescribeFeatureGroup",
                "sagemaker:ListFeatureGroups",
                "sagemaker:PutRecord",
                "sagemaker:GetRecord",
                "sagemaker:BatchGetRecord",
            ],
            resources=[
                f"arn:aws:sagemaker:{self.region}:{self.account}:feature-group/my-mlops-feature-group-v2",
                f"arn:aws:sagemaker:{self.region}:{self.account}:feature-group/my-mlops-user-interactions-v1",
            ],
        ))

        # ========================================
        # Feature Store (운영 Feature Store 공유 사용)
        # ========================================
        enable_feature_group = False  # 개발망에서는 새로 생성하지 않음
        use_existing_feature_group = True  # 운영 Feature Store 참조
        feature_group_name = f"my-mlops-feature-group-v2"  # 운영 Feature Store 이름

        if enable_feature_group and not use_existing_feature_group:
            fg = FeatureGroup(
                self,
                "DevFeatureGroup",
                feature_group_name=feature_group_name,
                s3_uri=f"s3://{storage.data_bucket.bucket_name}/feature-store/",
                role=sm_exec.role,
                kms_key_arn=kms.key.key_arn,
                record_identifier_name="id",
                event_time_name="event_time",
            )

            if storage.data_bucket.policy:
                fg.feature_group.node.add_dependency(storage.data_bucket.policy)
                
            self.feature_group_name = feature_group_name
        else:
            # 운영 Feature Store 참조
            self.feature_group_name = "my-mlops-feature-group-v2"  # 또는 기존 운영 FG 이름

        # 사용자 상호작용 데이터용 Feature Group (운영 공유)
        # 개발에서도 운영 Feature Store 사용
        shared_user_interaction_fg_name = "my-mlops-user-interactions-v1"  # 운영과 동일
        self.user_interaction_fg_name = shared_user_interaction_fg_name

        # ========================================
        # SageMaker CI/CD (개발 전용 MLOps 파이프라인)
        # ========================================
        enable_sm_ci = True  # 개발망에서는 기본 활성화
        if enable_sm_ci and cicd is not None:
            sm_pkg_group_name = f"{name_prefix}-pkg"
            sm_endpoint_name = f"{name_prefix}-endpoint"
            sm_instance_type = "ml.m5.large"
            sm_train_image = f"366743142698.dkr.ecr.{self.region}.amazonaws.com/sagemaker-xgboost:1.7-1"
            ct_cron = ""

            ModelRegistry(self, "DevModelRegistry", group_name=sm_pkg_group_name)

            source_stage = cicd.pipeline.stages[0]
            source_output = source_stage.actions[0].action_properties.outputs[0]

            # Cross-repo 배포 액션 (SageMaker CI/CD 전에 정의)
            deploy_to_prod_action = None
            if cfg.enable_pipeline:
                deploy_to_prod_action = codepipeline_actions.CodeBuildAction(
                    action_name="DeployToProd",
                    project=cross_repo_deploy,
                    input=source_output,
                    run_order=2,  # 승인 후 실행
                )

            sm_cicd = SageMakerCiCd(
                self, "DevSmCiCd",
                artifacts_bucket=storage.artifacts_bucket,
                data_bucket=storage.data_bucket,
                codebuild_role=iam.codebuild_role,
                pipeline=cicd.pipeline,
                source_output=source_output,
                pkg_group_name=sm_pkg_group_name,
                train_image_uri=sm_train_image,
                sm_exec_role_arn=sm_exec.role.role_arn,
                sm_instance_type=sm_instance_type,
                endpoint_name=sm_endpoint_name,
                ct_schedule_cron=ct_cron,
                use_sm_pipeline=True,  # SageMaker Pipeline 사용
                use_feature_store=True,
                feature_group_name=self.feature_group_name,
            )

            # 파이프라인 Deploy 스테이지 수정 - Cross-repo 배포 액션 추가
            # SageMakerCiCd가 생성한 Deploy 스테이지를 찾아서 수정
            if deploy_to_prod_action and cfg.enable_pipeline:
                deploy_stage = None
                for stage in cicd.pipeline.stages:
                    if stage.stage_name == "Deploy":
                        deploy_stage = stage
                        break
                
                if deploy_stage:
                    # Deploy 스테이지에 Cross-repo 배포 액션 추가
                    deploy_stage.add_action(deploy_to_prod_action)

            # 추가 IAM 권한 (운영망과 동일)
            iam.codebuild_role.add_to_policy(iam_cdk.PolicyStatement(
                sid="ReadSageMakerTrainingLogs",
                actions=[
                    "logs:DescribeLogStreams",
                    "logs:GetLogEvents",
                    "logs:FilterLogEvents",
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/sagemaker/*",
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/sagemaker/*:log-stream:*",
                ],
            ))
            iam.codebuild_role.add_to_policy(iam_cdk.PolicyStatement(
                actions=["logs:DescribeLogGroups"],
                resources=["*"],
            ))
            iam.codebuild_role.add_to_policy(iam_cdk.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[sm_exec.role.role_arn],
            ))

            CfnOutput(self, "DevSmPackageGroup", value=sm_pkg_group_name)
            CfnOutput(self, "DevSmEndpointName", value=sm_endpoint_name)

        # ========================================
        # 출력값들 (개발 전용)
        # ========================================
        CfnOutput(self, "DevArtifactsBucket", value=storage.artifacts_bucket.bucket_name)
        CfnOutput(self, "DevDataBucket", value=storage.data_bucket.bucket_name)
        CfnOutput(self, "DevLogsBucket", value=storage.logs_bucket.bucket_name)
        CfnOutput(self, "DevEcrRepoUri", value=ecr.repo.repository_uri)
        CfnOutput(self, "DevSmExecRoleArn", value=sm_exec.role.role_arn)
        if vpc:
            CfnOutput(self, "DevVpcId", value=vpc.vpc_id)

        # SageMaker Studio (개발 전용)
        enable_studio = True
        if enable_studio and vpc:
            studio_domain_name = f"{cfg.project_name}-dev-{cfg.env_name}-studio"
            studio_user = "dev-admin"
            Studio(
                self,
                "DevStudio",
                vpc=vpc,
                kms_key=kms.key,
                domain_name=studio_domain_name,
                user_name=studio_user,
                s3_access_buckets=[storage.data_bucket, storage.artifacts_bucket],
            )

        # 다른 스택에서 참조할 수 있도록 속성 노출
        self.data_bucket = storage.data_bucket
        self.artifacts_bucket = storage.artifacts_bucket
        self.vpc = vpc
