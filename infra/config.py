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
    use_codestar_connection: bool
    codestar_connection_arn: str
    codestar_repo_owner: str
    codestar_repo_name: str

def load_cfg(app) -> Config:
    def to_bool(val):
        if isinstance(val, bool):
            return val
        if val is None:
            return False
        return str(val).lower() in ("1", "true", "yes", "y", "on")

    def ctx(key, default):
        return app.node.try_get_context(key) or default

    return Config(
        project_name = ctx("project_name", "my-mlops"),
        env_name = ctx("env_name", "dev"),
        region = ctx("region", "ap-northeast-2"),
        include_vpc = to_bool(ctx("include_vpc", True)),
        enable_pipeline = to_bool(ctx("enable_pipeline", True)),
        codecommit_repo_name = ctx("codecommit_repo_name", "my-mlops-repo"),
        pipeline_branch = ctx("pipeline_branch", "main"),
        artifact_bucket_lifecycle_days = int(ctx("artifact_bucket_lifecycle_days", 90)),
        ecr_untagged_keep = int(ctx("ecr_untagged_keep", 20)),
        use_codestar_connection = to_bool(ctx("use_codestar_connection", False)),
        codestar_connection_arn = ctx("codestar_connection_arn", ""),
        codestar_repo_owner = ctx("codestar_repo_owner", ""),
        codestar_repo_name = ctx("codestar_repo_name", ctx("codecommit_repo_name", "my-mlops-repo")),
    )
