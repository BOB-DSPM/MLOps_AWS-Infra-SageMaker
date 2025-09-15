from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    aws_sagemaker as sm,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as cpactions,
    aws_events as events,
    aws_events_targets as targets,
    aws_logs as logs,
    aws_iam as iam,
    aws_s3 as s3,
)


class ModelRegistry(Construct):
    def __init__(self, scope: Construct, id: str, *, group_name: str):
        super().__init__(scope, id)

        self.group = sm.CfnModelPackageGroup(
            self,
            "Group",
            model_package_group_name=group_name,
            model_package_group_description="Model registry for MLOps",
        )


class SageMakerCiCd(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        artifacts_bucket: s3.IBucket,
        data_bucket: s3.IBucket,
        codebuild_role: iam.IRole,
        pipeline: codepipeline.Pipeline,
        source_output: codepipeline.Artifact,
        pkg_group_name: str,
        train_image_uri: str | None,
        sm_exec_role_arn: str,
        sm_instance_type: str,
        endpoint_name: str,
        ct_schedule_cron: str | None = None,
    ):
        super().__init__(scope, id)

        data_bucket.grant_read_write(codebuild_role)
        artifacts_bucket.grant_read_write(codebuild_role)

        base_cmd = (
            "python ml/pipeline.py "
            f"--pkg-group {pkg_group_name} "
            f"--instance-type {sm_instance_type} "
            f"--s3-data-prefix s3://{data_bucket.bucket_name}/ct/input/"
        )
        if train_image_uri and train_image_uri.strip():
            base_cmd += f" --train-image-uri {train_image_uri.strip()}"

        train_register = codebuild.Project(
            self,
            "TrainRegister",
            role=codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=False,
            ),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=logs.LogGroup(
                        self,
                        "TrainLogs",
                        retention=logs.RetentionDays.ONE_MONTH,
                    )
                )
            ),
            environment_variables={
                "SM_EXEC_ROLE_ARN": codebuild.BuildEnvironmentVariable(
                    value=sm_exec_role_arn
                )
            },
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "runtime-versions": {"python": "3.11"},
                            "commands": [
                                "pip install --upgrade pip",
                                "pip install boto3 sagemaker==2.* pandas numpy",
                            ],
                        },
                        "build": {
                            "commands": [
                                "echo 'TRAIN & REGISTER'",
                                base_cmd,
                            ],
                        },
                    },
                    "artifacts": {"files": ["**/*"]},
                }
            ),
        )

        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateTrainingJob",
                    "sagemaker:DescribeTrainingJob",

                    "sagemaker:CreateModelPackage",
                    "sagemaker:DescribeModelPackage",
                    "sagemaker:ListModelPackages",

                    "sagemaker:CreateModelPackageGroup",
                    "sagemaker:DescribeModelPackageGroup",
                    "sagemaker:ListModelPackageGroups",
                    "sagemaker:PutModelPackageGroupPolicy",

                    "sagemaker:AddTags",
                ],
                resources=["*"],
            )
        )
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:GetLogEvents",
                    "logs:FilterLogEvents",
                ],
                resources=["*"],
            )
        )
        codebuild_role.add_to_policy(
            iam.PolicyStatement(actions=["iam:PassRole"], resources=[sm_exec_role_arn])
        )
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=["*"],
            )
        )

        deploy = codebuild.Project(
            self,
            "Deploy",
            role=codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=False,
            ),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=logs.LogGroup(
                        self, "DeployLogs", retention=logs.RetentionDays.ONE_MONTH
                    )
                )
            ),
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "runtime-versions": {"python": "3.11"},
                            "commands": ["pip install boto3"],
                        },
                        "build": {
                            "commands": [
                                "python - <<'PY'\n"
                                "import boto3, time\n"
                                f"GROUP='{pkg_group_name}'\n"
                                f"EP='{endpoint_name}'\n"
                                f"ROLE='{sm_exec_role_arn}'\n"
                                f"ITYPE='{sm_instance_type}'\n"
                                "sm=boto3.client('sagemaker')\n"
                                "resp=sm.list_model_packages(ModelPackageGroupName=GROUP, SortBy='CreationTime', SortOrder='Descending')\n"
                                "if not resp['ModelPackageSummaryList']:\n"
                                "  raise SystemExit('No model package found in group: '+GROUP)\n"
                                "mp=resp['ModelPackageSummaryList'][0]['ModelPackageArn']\n"
                                "# 승인(이미 Approved 여도 안전)\n"
                                "sm.update_model_package(ModelPackageArn=mp, ModelApprovalStatus='Approved', ApprovalDescription='Approved by CodePipeline')\n"
                                "ts=str(int(time.time()))\n"
                                "mname=f'{GROUP}-model-'+ts\n"
                                "cfg=f'{GROUP}-cfg-'+ts\n"
                                "sm.create_model(ModelName=mname, ExecutionRoleArn=ROLE, Containers=[{'ModelPackageName': mp}])\n"
                                "try:\n"
                                "  sm.describe_endpoint(EndpointName=EP)\n"
                                "  sm.create_endpoint_config(EndpointConfigName=cfg, ProductionVariants=[{'ModelName': mname,'VariantName':'AllTraffic','InitialInstanceCount':1,'InstanceType':ITYPE,'InitialVariantWeight':1.0}])\n"
                                "  sm.update_endpoint(EndpointName=EP, EndpointConfigName=cfg)\n"
                                "except sm.exceptions.ClientError:\n"
                                "  sm.create_endpoint_config(EndpointConfigName=cfg, ProductionVariants=[{'ModelName': mname,'VariantName':'AllTraffic','InitialInstanceCount':1,'InstanceType':ITYPE,'InitialVariantWeight':1.0}])\n"
                                "  sm.create_endpoint(EndpointName=EP, EndpointConfigName=cfg)\n"
                                "print('DEPLOYED to', EP)\n"
                                "PY"
                            ],
                        },
                    },
                }
            ),
        )

        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sagemaker:CreateModel",
                    "sagemaker:CreateEndpointConfig",
                    "sagemaker:CreateEndpoint",
                    "sagemaker:UpdateEndpoint",
                    "sagemaker:DescribeEndpoint",
                    "sagemaker:DescribeModel",
                    "sagemaker:ListModelPackages",
                    "sagemaker:DescribeModelPackage",
                    "sagemaker:UpdateModelPackage",         
                ],
                resources=["*"],
            )
        )
        codebuild_role.add_to_policy(
            iam.PolicyStatement(actions=["iam:PassRole"], resources=[sm_exec_role_arn])
        )

        train_out = codepipeline.Artifact(artifact_name="TrainOut")

        pipeline.add_stage(
            stage_name="TrainRegister",
            actions=[
                cpactions.CodeBuildAction(
                    action_name="TrainRegister",
                    project=train_register,
                    input=source_output,
                    outputs=[train_out],
                )
            ],
        )
        pipeline.add_stage(
            stage_name="Approve",
            actions=[cpactions.ManualApprovalAction(action_name="ManualApprove")],
        )
        pipeline.add_stage(
            stage_name="Deploy",
            actions=[
                cpactions.CodeBuildAction(
                    action_name="DeployApproved",
                    project=deploy,
                    input=train_out,
                )
            ],
        )

        if ct_schedule_cron and ct_schedule_cron.strip():
            rule = events.Rule(
                self,
                "CtSchedule",
                schedule=events.Schedule.expression(ct_schedule_cron),
            )
            rule.add_target(targets.CodePipeline(pipeline=pipeline))
