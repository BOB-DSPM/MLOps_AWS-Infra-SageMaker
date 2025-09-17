# infra/sagemaker_ci.py
from __future__ import annotations

from constructs import Construct
from aws_cdk import (
    Fn,
    Stack,
    CfnParameter,
    CfnCondition,
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
    def __init__(self, scope: Construct, id: str, *, group_name: str, use_existing: bool = True):
        super().__init__(scope, id)

        self.param_group_name = CfnParameter(
            self, "ModelPackageGroupName",
            type="String",
            default=group_name,
            description="SageMaker Model Package Group name to use or create.",
        )
        self.param_use_existing = CfnParameter(
            self, "UseExistingModelPackageGroup",
            type="String",
            allowed_values=["true", "false"],
            default="true" if use_existing else "false",
            description="true → reuse existing MPG; false → create new MPG",
        )

        self.cond_create = CfnCondition(
            self,
            "CreateModelPackageGroupCondition",
            expression=Fn.condition_equals(self.param_use_existing.value_as_string, "false"),
        )

        self._group = sm.CfnModelPackageGroup(
            self,
            "Group",
            model_package_group_name=self.param_group_name.value_as_string,
            model_package_group_description="Model registry for MLOps",
        )
        self._group.cfn_options.condition = self.cond_create

        self.group_name: str = self.param_group_name.value_as_string
        self.group_arn: str = Stack.of(self).format_arn(
            service="sagemaker",
            resource="model-package-group",
            resource_name=self.group_name,
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

        train_logs = logs.LogGroup(self, "TrainLogs", retention=logs.RetentionDays.ONE_MONTH)
        train_logs.grant_write(codebuild_role)

        train_env = {
            "SM_EXEC_ROLE_ARN": codebuild.BuildEnvironmentVariable(value=sm_exec_role_arn),
            "MODEL_PACKAGE_GROUP_NAME": codebuild.BuildEnvironmentVariable(value=pkg_group_name),
            "SM_INSTANCE_TYPE": codebuild.BuildEnvironmentVariable(value=sm_instance_type),
            "TRAIN_IMAGE_URI": codebuild.BuildEnvironmentVariable(value=(train_image_uri or "")),
            "DATA_BUCKET": codebuild.BuildEnvironmentVariable(value=data_bucket.bucket_name),
        }

        train_register = codebuild.Project(
            self,
            "TrainRegister",
            role=codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=False,
            ),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(log_group=train_logs)
            ),
            environment_variables=train_env,
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
                                "echo 'Ensure Model Package Group exists...'",
                                "python - <<'PY'\n"
                                "import os, sys, boto3\n"
                                "from botocore.exceptions import ClientError\n"
                                "sm=boto3.client('sagemaker')\n"
                                "group=os.environ['MODEL_PACKAGE_GROUP_NAME']\n"
                                "try:\n"
                                "    sm.describe_model_package_group(ModelPackageGroupName=group)\n"
                                "    print('[MPG] exists:', group)\n"
                                "except ClientError as e:\n"
                                "    if e.response['Error']['Code']=='ValidationException' and 'does not exist' in e.response['Error']['Message']:\n"
                                "        sm.create_model_package_group(ModelPackageGroupName=group, ModelPackageGroupDescription='Created by CodeBuild')\n"
                                "        print('[MPG] created:', group)\n"
                                "    else:\n"
                                "        print('[ERROR] MPG check:', e, file=sys.stderr)\n"
                                "        sys.exit(1)\n"
                                "PY",
                                "echo 'TRAIN & REGISTER (inline script, fallback to XGBoost if custom image fails)'",
                                "python - <<'PY'\n"
                                "import io, json, os, sys, time, tempfile\n"
                                "import boto3, numpy as np, pandas as pd\n"
                                "import sagemaker\n"
                                "from sagemaker.estimator import Estimator\n"
                                "from sagemaker.inputs import TrainingInput\n"
                                "from sagemaker import image_uris\n"
                                "\n"
                                "def ensure_dataset(s3_prefix_uri: str) -> str:\n"
                                "    s3 = boto3.client('s3')\n"
                                "    b, p = s3_prefix_uri.replace('s3://','').split('/',1)\n"
                                "    p = p.rstrip('/')  # ✅ strip first to avoid f-string escape issues\n"
                                "    def exists(k: str) -> bool:\n"
                                "        try:\n"
                                "            s3.head_object(Bucket=b, Key=k)\n"
                                "            return True\n"
                                "        except Exception:\n"
                                "            return False\n"
                                "    train_key = f\"{p}/train/data.csv\"\n"
                                "    val_key   = f\"{p}/validation/data.csv\"\n"
                                "    for k in [train_key, val_key]:\n"
                                "        if exists(k):\n"
                                "            continue\n"
                                "        X = np.random.randn(200,5)\n"
                                "        y = (X.sum(axis=1) > 0).astype(int)\n"
                                "        df = pd.DataFrame(np.column_stack([y, X]))\n"
                                "        with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:\n"
                                "            df.to_csv(f.name, index=False, header=False)\n"
                                "            s3.upload_file(f.name, b, k)\n"
                                "    return f\"s3://{b}/{p}/\"\n"
                                "\n"
                                "def train_once(image_uri: str|None, role: str, instance_type: str, s3_prefix: str):\n"
                                "    sm_sess = sagemaker.Session()\n"
                                "    if not image_uri:\n"
                                "        image_uri = image_uris.retrieve(framework='xgboost', region=sm_sess.boto_region_name, version='1.7-1')\n"
                                "        print(f\"[INFO] Using AWS official XGBoost: {image_uri}\")\n"
                                "    else:\n"
                                "        print(f\"[INFO] Using custom training image: {image_uri}\")\n"
                                "    est = Estimator(\n"
                                "        image_uri=image_uri,\n"
                                "        role=os.environ['SM_EXEC_ROLE_ARN'],\n"
                                "        instance_count=1,\n"
                                "        instance_type=os.environ['SM_INSTANCE_TYPE'],\n"
                                "        sagemaker_session=sm_sess,\n"
                                "        enable_network_isolation=False,\n"
                                "        output_path=s3_prefix+'model/',\n"
                                "    )\n"
                                "    est.set_hyperparameters(objective='binary:logistic', num_round=50, eval_metric='auc', verbosity=1)\n"
                                "    train_ch = TrainingInput(s3_data=s3_prefix+'train/', content_type='text/csv', s3_data_type='S3Prefix', input_mode='File')\n"
                                "    val_ch   = TrainingInput(s3_data=s3_prefix+'validation/', content_type='text/csv', s3_data_type='S3Prefix', input_mode='File')\n"
                                "    job_name = f\"train-{int(time.time())}\"\n"
                                "    est.fit(job_name=job_name, inputs={'train': train_ch, 'validation': val_ch}, wait=True, logs=True)\n"
                                "    return est, sm_sess\n"
                                "\n"
                                "def main():\n"
                                "    GROUP = os.environ['MODEL_PACKAGE_GROUP_NAME']\n"
                                "    DATA_BUCKET = os.environ['DATA_BUCKET']\n"
                                "    TRAIN_IMG = (os.environ.get('TRAIN_IMAGE_URI') or '').strip()\n"
                                "    s3_prefix = ensure_dataset(f's3://{DATA_BUCKET}/ct/input/')\n"
                                "\n"
                                "    # Try custom image first; on failure, fallback to official XGBoost\n"
                                "    try:\n"
                                "        est, sm_sess = train_once(TRAIN_IMG or None, os.environ['SM_EXEC_ROLE_ARN'], os.environ['SM_INSTANCE_TYPE'], s3_prefix)\n"
                                "    except Exception as e:\n"
                                "        print('[WARN] Custom image training failed, fallback to XGBoost. Reason:', str(e))\n"
                                "        est, sm_sess = train_once(None, os.environ['SM_EXEC_ROLE_ARN'], os.environ['SM_INSTANCE_TYPE'], s3_prefix)\n"
                                "\n"
                                "    # Write dummy metric\n"
                                "    metrics = {'dummy:auc': 0.75}\n"
                                "    s3 = boto3.client('s3')\n"
                                "    bucket = s3_prefix.split('/')[2]\n"
                                "    kprefix = '/'.join(s3_prefix.split('/')[3:]).rstrip('/')\n"
                                "    mkey = f\"{kprefix}/metrics.json\"\n"
                                "    s3.put_object(Bucket=bucket, Key=mkey, Body=io.BytesIO(json.dumps(metrics).encode()), ContentType='application/json')\n"
                                "    metrics_s3 = f's3://{bucket}/{mkey}'\n"
                                "\n"
                                "    # Register model package\n"
                                "    sm = boto3.client('sagemaker')\n"
                                "    container = [{'Image': est.image_uri, 'ModelDataUrl': est.model_data}]\n"
                                "    pkg = sm.create_model_package(\n"
                                "        ModelPackageGroupName=GROUP,\n"
                                "        InferenceSpecification={\n"
                                "            'Containers': container,\n"
                                "            'SupportedContentTypes': ['text/csv'],\n"
                                "            'SupportedResponseMIMETypes': ['text/csv']\n"
                                "        },\n"
                                "        ModelMetrics={'ModelQuality': {'Statistics': {'ContentType': 'application/json', 'S3Uri': metrics_s3}}},\n"
                                "        ModelApprovalStatus='PendingManualApproval',\n"
                                "    )\n"
                                "    try:\n"
                                "        region = sm_sess.boto_region_name\n"
                                "        account = boto3.client('sts').get_caller_identity()['Account']\n"
                                "        group_arn = f'arn:aws:sagemaker:{region}:{account}:model-package-group/{GROUP}'\n"
                                "        sm.add_tags(ResourceArn=group_arn, Tags=[{'Key': 'Project', 'Value': 'my-mlops'}])\n"
                                "    except Exception as te:\n"
                                "        print('[WARN] add_tags ignored:', te)\n"
                                "    print(json.dumps({'model_package_arn': pkg['ModelPackageArn'], 'metrics': metrics}))\n"
                                "\n"
                                "if __name__ == '__main__':\n"
                                "    main()\n"
                                "PY",
                            ],
                        },
                    },
                    "artifacts": {"files": ["**/*"]},
                }
            ),
        )

        deploy_logs = logs.LogGroup(self, "DeployLogs", retention=logs.RetentionDays.ONE_MONTH)
        deploy_logs.grant_write(codebuild_role)

        deploy = codebuild.Project(
            self,
            "Deploy",
            role=codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=False,
            ),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(log_group=deploy_logs)
            ),
            environment_variables={
                "MODEL_PACKAGE_GROUP_NAME": codebuild.BuildEnvironmentVariable(value=pkg_group_name),
                "ENDPOINT_NAME": codebuild.BuildEnvironmentVariable(value=endpoint_name),
                "SM_EXEC_ROLE_ARN": codebuild.BuildEnvironmentVariable(value=sm_exec_role_arn),
                "SM_INSTANCE_TYPE": codebuild.BuildEnvironmentVariable(value=sm_instance_type),
            },
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
                                "import os, boto3, time\n"
                                "GROUP=os.environ['MODEL_PACKAGE_GROUP_NAME']\n"
                                "EP=os.environ['ENDPOINT_NAME']\n"
                                "ROLE=os.environ['SM_EXEC_ROLE_ARN']\n"
                                "ITYPE=os.environ['SM_INSTANCE_TYPE']\n"
                                "sm=boto3.client('sagemaker')\n"
                                "resp=sm.list_model_packages(ModelPackageGroupName=GROUP, SortBy='CreationTime', SortOrder='Descending')\n"
                                "if not resp['ModelPackageSummaryList']:\n"
                                "  raise SystemExit('No model package found in group: '+GROUP)\n"
                                "mp=resp['ModelPackageSummaryList'][0]['ModelPackageArn']\n"
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
                    "sagemaker:CreateModel",
                    "sagemaker:CreateEndpointConfig",
                    "sagemaker:CreateEndpoint",
                    "sagemaker:UpdateEndpoint",
                    "sagemaker:DescribeEndpoint",
                    "sagemaker:DescribeModel",
                    "sagemaker:UpdateModelPackage",
                ],
                resources=["*"],
            )
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
        codebuild_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:GetLogEvents",
                ],
                resources=["*"],
            )
        )
        codebuild_role.add_to_policy(iam.PolicyStatement(actions=["iam:PassRole"], resources=[sm_exec_role_arn]))

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
        pipeline.add_stage(stage_name="Approve", actions=[cpactions.ManualApprovalAction(action_name="ManualApprove")])
        pipeline.add_stage(
            stage_name="Deploy",
            actions=[cpactions.CodeBuildAction(action_name="DeployApproved", project=deploy, input=train_out)],
        )

        if ct_schedule_cron and ct_schedule_cron.strip():
            rule = events.Rule(self, "CtSchedule", schedule=events.Schedule.expression(ct_schedule_cron))
            rule.add_target(targets.CodePipeline(pipeline=pipeline))
