import os, sys
sys.path.append(os.path.dirname(__file__)) 

from aws_cdk import (
    App, Environment, Tags
)
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
# 기존 운영 환경은 My-mlops-BaseStack 그대로 유지
# ========================================

# 모델 추론용 스택 (별도 VPC) - 기존 운영망 참조
inference_stack = ModelInferenceStack(
    app, f"{cfg.project_name.capitalize()}-InferenceStack",
    sagemaker_endpoint_name=f"{cfg.project_name}-{cfg.env_name}-endpoint",
    model_package_group_name=f"{cfg.project_name}-{cfg.env_name}-pkg",
    user_interaction_fg_name=f"{cfg.project_name}-{cfg.env_name}-user-interactions-v1",
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
    dev_vpc_id="vpc-077d29cb1c2eac9ea",  # 개발용 VPC ID 직접 지정
    env=env
)

# 의존성 설정 - 개발 MLOps는 개발 VPC 이후에 생성
dev_mlops_stack.add_dependency(dev_vpc_stack)

# ========================================
# 태그 설정
# ========================================
# 기존 운영 환경은 My-mlops-BaseStack에서 이미 관리됨

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

