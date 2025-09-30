import os, sys
sys.path.append(os.path.dirname(__file__)) 

from aws_cdk import (
    App, Environment, Tags
)
from stacks.base_stack import BaseStack
from stacks.inference_stack import ModelInferenceStack
from stacks.dev_vpc_stack import DevVPCStack
from stacks.dev_mlops_stack import DevMLOpsStack
from infra.config import load_cfg

app = App()
cfg = load_cfg(app)

env = Environment(
    account = os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region = "ap-northeast-2",
)

# ========================================
# 운영 환경 (BaseStack)
# ========================================
base_stack = BaseStack(
    app, f"{cfg.project_name.capitalize()}-BaseStack",
    cfg=cfg,
    env=env
)

# 모델 추론용 스택 (별도 VPC) - 작동하는 dev 엔드포인트 사용
inference_stack = ModelInferenceStack(
    app, f"{cfg.project_name.capitalize()}-InferenceStack",
    sagemaker_endpoint_name=f"{cfg.project_name}-dev-endpoint",  # 작동하는 dev 엔드포인트 사용
    model_package_group_name=f"{cfg.project_name}-dev-pkg",      # 작동하는 dev 모델 패키지 그룹 사용
    user_interaction_fg_name=f"{cfg.project_name}-dev-user-interactions-v1",  # dev Feature Group 사용
    env=env
)

# ========================================
# 개발용 VPC 스택 (별도 VPC)
# ========================================
dev_vpc_stack = DevVPCStack(
    app, f"{cfg.project_name.capitalize()}-DevVpcStack",
    cfg=cfg,
    env=env
)

# ========================================
# 개발용 MLOps 스택 (운영망 파이프라인 복사본)
# ========================================
dev_mlops_stack = DevMLOpsStack(
    app, f"{cfg.project_name.capitalize()}-DevMLOpsStack",
    cfg=cfg,
    dev_vpc=dev_vpc_stack.dev_vpc,  # VPC 객체 직접 전달
    env=env
)

# 의존성 설정
dev_mlops_stack.add_dependency(dev_vpc_stack)
# inference_stack.add_dependency(base_stack)  # 추론 서비스는 운영 환경 이후
inference_stack.add_dependency(base_stack)  # 추론 서비스는 운영 환경 이후

# ========================================
# 태그 설정
# ========================================
Tags.of(base_stack).add("Project", cfg.project_name)
Tags.of(base_stack).add("Env", "production")
Tags.of(base_stack).add("ManagedBy", "cdk")

# Tags.of(inference_stack).add("Project", cfg.project_name)
# Tags.of(inference_stack).add("Env", "production-inference")
# Tags.of(inference_stack).add("ManagedBy", "cdk")
Tags.of(inference_stack).add("Project", cfg.project_name)
Tags.of(inference_stack).add("Env", "production-inference")
Tags.of(inference_stack).add("ManagedBy", "cdk")

Tags.of(dev_vpc_stack).add("Project", cfg.project_name)
Tags.of(dev_vpc_stack).add("Env", "development")
Tags.of(dev_vpc_stack).add("ManagedBy", "cdk")

Tags.of(dev_mlops_stack).add("Project", cfg.project_name)
Tags.of(dev_mlops_stack).add("Env", "development")
Tags.of(dev_mlops_stack).add("ManagedBy", "cdk")

app.synth()

