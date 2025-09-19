import argparse
import os
import boto3
from sagemaker.workflow.pipeline import Pipeline
from sagemaker.workflow.parameters import (
    ParameterString,
    ParameterFloat,
    ParameterInteger,
)
from sagemaker.workflow.steps import CacheConfig, ProcessingStep, TrainingStep
from sagemaker.workflow.step_collections import RegisterModel
from sagemaker.workflow.properties import PropertyFile
from sagemaker.workflow.functions import Join
from sagemaker.workflow.condition_step import (
    ConditionStep,
    JsonGet,
)
from sagemaker.workflow.conditions import ConditionGreaterThanOrEqualTo
from sagemaker.processing import ScriptProcessor, ProcessingInput, ProcessingOutput
from sagemaker.sklearn.processing import SKLearnProcessor
from sagemaker.estimator import Estimator
from sagemaker.inputs import TrainingInput
from sagemaker import image_uris
from sagemaker.workflow.pipeline_context import PipelineSession


def get_pipeline(region: str, role: str) -> Pipeline:
    # Use PipelineSession to ensure steps are compiled into a pipeline graph
    # instead of executing immediately (avoids JSON serialization of Parameters)
    sm_sess = PipelineSession()

    p_data_bucket = ParameterString(name="DataBucket", default_value=os.environ.get("DATA_BUCKET", ""))
    p_prefix = ParameterString(name="Prefix", default_value="pipelines/exp1")
    p_instance_type = ParameterString(name="InstanceType", default_value=os.environ.get("SM_INSTANCE_TYPE", "ml.m5.large"))
    default_train_image = image_uris.retrieve(framework="xgboost", region=sm_sess.boto_region_name, version="1.7-1")
    p_train_image = ParameterString(name="TrainImage", default_value=os.environ.get("TRAIN_IMAGE_URI", default_train_image))
    p_external_csv = ParameterString(name="ExternalCsvUri", default_value=os.environ.get("EXTERNAL_CSV_URI", ""))
    p_use_fs = ParameterString(name="UseFeatureStore", default_value=os.environ.get("USE_FEATURE_STORE", "true"))
    p_fg_name = ParameterString(name="FeatureGroupName", default_value=os.environ.get("FEATURE_GROUP_NAME", ""))
    p_model_package_group_name = ParameterString(name="ModelPackageGroupName", default_value=os.environ.get("MODEL_PACKAGE_GROUP_NAME", "model-pkg"))
    p_auc_threshold = ParameterFloat(name="AucThreshold", default_value=0.65)
    p_num_round = ParameterInteger(name="NumRound", default_value=50)

    cache = CacheConfig(enable_caching=False, expire_after="PT1H")

    # Upload local processing scripts to an existing S3 bucket to avoid default bucket creation
    data_bucket_env = os.environ.get("DATA_BUCKET", "")
    if not data_bucket_env:
        raise SystemExit("DATA_BUCKET env var must be set for pipeline compilation")
    s3 = boto3.client("s3")
    base_dir = os.path.dirname(__file__)
    scripts = {
        "extract": os.path.join(base_dir, "steps", "01_extract.py"),
        "validate": os.path.join(base_dir, "steps", "02_validate.py"),
        "preprocess": os.path.join(base_dir, "steps", "03_preprocess.py"),
        "evaluate": os.path.join(base_dir, "steps", "04_evaluate.py"),
    }
    s3_prefix_scripts = "pipelines/scripts"
    code_uris = {}
    for name, path in scripts.items():
        key = f"{s3_prefix_scripts}/{os.path.basename(path)}"
        s3.upload_file(path, data_bucket_env, key)
        code_uris[name] = f"s3://{data_bucket_env}/{key}"

    extract = SKLearnProcessor(
        framework_version="1.2-1",
        role=role,
        instance_type=p_instance_type,
        instance_count=1,
        sagemaker_session=sm_sess,
    )
    extract_args = extract.run(
        code=code_uris["extract"],
        inputs=[],
        outputs=[
            ProcessingOutput(
                output_name="train",
                source="/opt/ml/processing/train",
                destination=Join(on="", values=["s3://", p_data_bucket, "/", p_prefix, "/extract/train"]),
            ),
            ProcessingOutput(
                output_name="validation",
                source="/opt/ml/processing/validation",
                destination=Join(on="", values=["s3://", p_data_bucket, "/", p_prefix, "/extract/validation"]),
            ),
        ],
        arguments=[
            "--s3", Join(on="", values=["s3://", p_data_bucket, "/", p_prefix]),
            "--csv", p_external_csv,
            "--use-feature-store", p_use_fs,
            "--feature-group-name", p_fg_name,
        ],
    )
    extract_step = ProcessingStep(name="Extract", step_args=extract_args)

    validate = SKLearnProcessor(
        framework_version="1.2-1",
        role=role,
        instance_type=p_instance_type,
        instance_count=1,
        sagemaker_session=sm_sess,
    )
    validate_args = validate.run(
        code=code_uris["validate"],
        inputs=[
            ProcessingInput(source=extract_step.properties.ProcessingOutputConfig.Outputs[0].S3Output.S3Uri, destination="/opt/ml/processing/train"),
            ProcessingInput(source=extract_step.properties.ProcessingOutputConfig.Outputs[1].S3Output.S3Uri, destination="/opt/ml/processing/validation"),
        ],
        outputs=[
            ProcessingOutput(
                output_name="report",
                source="/opt/ml/processing/report",
                destination=Join(on="", values=["s3://", p_data_bucket, "/", p_prefix, "/validate/report"]),
            )
        ],
    )
    validate_step = ProcessingStep(name="Validate", step_args=validate_args)

    preprocess = SKLearnProcessor(
        framework_version="1.2-1",
        role=role,
        instance_type=p_instance_type,
        instance_count=1,
        sagemaker_session=sm_sess,
    )
    preprocess_args = preprocess.run(
        code=code_uris["preprocess"],
        inputs=[
            ProcessingInput(source=extract_step.properties.ProcessingOutputConfig.Outputs[0].S3Output.S3Uri, destination="/opt/ml/processing/train"),
            ProcessingInput(source=extract_step.properties.ProcessingOutputConfig.Outputs[1].S3Output.S3Uri, destination="/opt/ml/processing/validation"),
        ],
        outputs=[
            ProcessingOutput(
                output_name="train_pre",
                source="/opt/ml/processing/train_pre",
                destination=Join(on="", values=["s3://", p_data_bucket, "/", p_prefix, "/preprocess/train_pre"]),
            ),
            ProcessingOutput(
                output_name="validation_pre",
                source="/opt/ml/processing/validation_pre",
                destination=Join(on="", values=["s3://", p_data_bucket, "/", p_prefix, "/preprocess/validation_pre"]),
            ),
        ],
    )
    preprocess_step = ProcessingStep(name="Preprocess", step_args=preprocess_args)

    image = p_train_image
    train = Estimator(
        image_uri=image,
        role=role,
        instance_type=p_instance_type,
        instance_count=1,
        sagemaker_session=sm_sess,
        output_path=Join(on="", values=["s3://", p_data_bucket, "/", p_prefix, "/model"]),
        enable_network_isolation=False,
    )
    train.set_hyperparameters(objective="binary:logistic", num_round=p_num_round, eval_metric="auc", verbosity=1)
    train_args = train.fit(
        inputs={
            "train": TrainingInput(s3_data=preprocess_step.properties.ProcessingOutputConfig.Outputs[0].S3Output.S3Uri, content_type="text/csv"),
            "validation": TrainingInput(s3_data=preprocess_step.properties.ProcessingOutputConfig.Outputs[1].S3Output.S3Uri, content_type="text/csv"),
        }
    )
    train_step = TrainingStep(name="Train", step_args=train_args)

    eval_proc = ScriptProcessor(
        image_uri=image_uris.retrieve(framework="sklearn", region=sm_sess.boto_region_name, version="1.2-1"),
        role=role,
        instance_type=p_instance_type,
        instance_count=1,
        command=["python3"],
        sagemaker_session=sm_sess,
    )
    evaluation = PropertyFile(name="EvaluationReport", output_name="report", path="evaluation.json")
    eval_args = eval_proc.run(
        code=code_uris["evaluate"],
        inputs=[
            ProcessingInput(source=train_step.properties.ModelArtifacts.S3ModelArtifacts, destination="/opt/ml/processing/model"),
            ProcessingInput(source=preprocess_step.properties.ProcessingOutputConfig.Outputs[1].S3Output.S3Uri, destination="/opt/ml/processing/validation_pre"),
        ],
        outputs=[
            ProcessingOutput(
                output_name="report",
                source="/opt/ml/processing/report",
                destination=Join(on="", values=["s3://", p_data_bucket, "/", p_prefix, "/evaluate/report"]),
            )
        ],
    )
    eval_step = ProcessingStep(name="Evaluate", step_args=eval_args, property_files=[evaluation])

    # RegisterModel requires the estimator definition and concrete instance types.
    # Use a safe default instance type; deployment uses another stage later.
    reg = RegisterModel(
        name="RegisterModel",
        estimator=train,
        model_data=train_step.properties.ModelArtifacts.S3ModelArtifacts,
        content_types=["text/csv"],
        response_types=["text/csv"],
        inference_instances=["ml.m5.large"],
        transform_instances=["ml.m5.large"],
        model_package_group_name=p_model_package_group_name,
        approval_status="PendingManualApproval",
    )

    cond = ConditionStep(
        name="ModelQualityCheck",
        conditions=[
            ConditionGreaterThanOrEqualTo(
                left=JsonGet(step=eval_step, property_file=evaluation, json_path="metrics.auc.value"),
                right=p_auc_threshold,
            )
        ],
        if_steps=[reg],
        else_steps=[],
    )

    pipeline = Pipeline(
        name=os.environ.get("SM_PIPELINE_NAME", "mlops-pipeline"),
        parameters=[
            p_data_bucket,
            p_prefix,
            p_instance_type,
            p_train_image,
            p_external_csv,
            p_use_fs,
            p_fg_name,
            p_auc_threshold,
            p_num_round,
        ],
        steps=[extract_step, validate_step, preprocess_step, train_step, eval_step, cond],
        sagemaker_session=sm_sess,
    )
    return pipeline


def upsert_and_start(wait: bool = False):
    import boto3
    region = boto3.Session().region_name
    role = os.environ["SM_EXEC_ROLE_ARN"]
    pipe = get_pipeline(region, role)
    pipe.upsert(role_arn=role)
    
    # 파이프라인 실행 시 환경변수를 매개변수로 전달
    parameters = {}
    if os.environ.get("DATA_BUCKET"):
        parameters["DataBucket"] = os.environ["DATA_BUCKET"]
    if os.environ.get("PREFIX"):
        parameters["Prefix"] = os.environ["PREFIX"]
    if os.environ.get("EXTERNAL_CSV_URI"):
        parameters["ExternalCsvUri"] = os.environ["EXTERNAL_CSV_URI"]
    if os.environ.get("USE_FEATURE_STORE"):
        parameters["UseFeatureStore"] = os.environ["USE_FEATURE_STORE"]
    if os.environ.get("FEATURE_GROUP_NAME"):
        parameters["FeatureGroupName"] = os.environ["FEATURE_GROUP_NAME"]
    if os.environ.get("MODEL_PACKAGE_GROUP_NAME"):
        parameters["ModelPackageGroupName"] = os.environ["MODEL_PACKAGE_GROUP_NAME"]
    if os.environ.get("TRAIN_IMAGE_URI"):
        parameters["TrainImage"] = os.environ["TRAIN_IMAGE_URI"]
        
    exe = pipe.start(parameters=parameters)
    print("Started pipeline:", exe.arn)
    print("Parameters passed:", parameters)
    if wait:
        sm = boto3.client("sagemaker")
        while True:
            desc = sm.describe_pipeline_execution(PipelineExecutionArn=exe.arn)
            status = desc.get("PipelineExecutionStatus")
            if status in {"Succeeded", "Failed", "Stopped"}:
                print("Pipeline finished with status:", status)
                if status != "Succeeded":
                    raise SystemExit(f"Pipeline did not succeed: {status}")
                break
            import time
            time.sleep(15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    if args.run:
        upsert_and_start(wait=args.wait)
    else:
        import boto3
        region = boto3.Session().region_name
        role = os.environ["SM_EXEC_ROLE_ARN"]
        p = get_pipeline(region, role)
        print(p.definition())
