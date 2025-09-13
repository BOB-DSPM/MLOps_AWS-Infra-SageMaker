import os, sys
sys.path.append(os.path.dirname(__file__)) 

from aws_cdk import (
    App, Environment, Tags
)
from stacks.base_stack import BaseStack
from infra.config import load_cfg

app = App()
cfg = load_cfg(app)

env = Environment(
    account = os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region = "ap-northeast-2",
)

stack = BaseStack(app, f"{cfg.project_name.capitalize()}-BaseStack", cfg=cfg, env=env)

Tags.of(stack).add("Project", cfg.project_name)
Tags.of(stack).add("Env", cfg.env_name)
Tags.of(stack).add("ManagedBy", "cdk")

app.synth()

