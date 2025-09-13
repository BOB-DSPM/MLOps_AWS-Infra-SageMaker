from dataclasses import dataclass

@dataclass
class Config:
    project_name: str
    env_name: str
    region: str
    include_vpc: bool
    enable_pipeline: bool
    codecommit_repo_name: str
    pipeline_branch: str
    artifact_bucket_lifecycle_days: int
    ecr_untagged_keep: int

def load_cfg(app) -> Config:
    def ctx(key, default):
        return app.node.try_get_context(key) or default
    return Config(
        project_name = ctx("project_name", "my-mlops"),
        env_name = ctx("env_name", "dev"),
        region = ctx("env_name", "dev"),
        include_vpc = bool(ctx("enable_pipeline", True)),
        enable_pipeline = bool(ctx("enable_pipeline", True)),
        codecommit_repo_name = ctx("codecommit_repo_name", "my-mlops-repo"),
        pipeline_branch = ctx("pipeline_branch", "main"),
        artifact_bucket_lifecycle_days = int(ctx("artifact_bucket_lifecycle_days", 90)),
        ecr_untagged_keep = int(ctx("ecr_untagged_keep", 20)),
    )

