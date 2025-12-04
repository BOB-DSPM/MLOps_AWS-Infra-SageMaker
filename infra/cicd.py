from constructs import Construct
from aws_cdk import (
    aws_codecommit as codecommit,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as cpactions,
    aws_logs as logs,
)

class CiCdPipeline(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        repo_name: str,
        branch: str,
        artifacts_bucket,
        codebuild_role,
        pipeline_role,
        use_codestar_connection: bool = False,
        codestar_connection_arn: str | None = None,
        codestar_repo_owner: str | None = None,
        codestar_repo_name: str | None = None,
    ) -> None:
        super().__init__(scope, construct_id)

        self.repo = None
        self.repo_clone_url_http = None

        self.project = codebuild.PipelineProject(
            self, "Build",
            role=codebuild_role,
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=True,
            ),
            logging=codebuild.LoggingOptions(
                cloud_watch=codebuild.CloudWatchLoggingOptions(
                    log_group=logs.LogGroup(
                        self, "BuildLogs",
                        retention=logs.RetentionDays.ONE_MONTH
                    )
                )
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {
                        "runtime-versions": {"python": "3.11"},
                        "commands": [
                            "echo INSTALL",
                            "aws --version",
                            "python --version",
                        ],
                    },
                    "build": {
                        "commands": [
                            "echo BUILD on `date` in $AWS_DEFAULT_REGION",
                            "echo Commit=$CODEBUILD_RESOLVED_SOURCE_VERSION",
                        ],
                    },
                },
                "artifacts": {"files": ["**/*"], "base-directory": "."},
            }),
        )

        source_output = codepipeline.Artifact(artifact_name="Source")
        build_output  = codepipeline.Artifact(artifact_name="BuildOutput")

        self.pipeline = codepipeline.Pipeline(
            self, "Pipeline",
            role=pipeline_role,
            artifact_bucket=artifacts_bucket,
            restart_execution_on_update=True,
            pipeline_name=f"{repo_name}-pipeline",
            pipeline_type=codepipeline.PipelineType.V2,
        )

        if use_codestar_connection:
            if not (codestar_connection_arn and codestar_repo_owner and codestar_repo_name):
                raise ValueError("CodeStar connection requires ARN, repo owner, and repo name.")
            source_action = cpactions.CodeStarConnectionsSourceAction(
                action_name="CodeStarSource",
                owner=codestar_repo_owner,
                repo=codestar_repo_name,
                branch=branch,
                connection_arn=codestar_connection_arn,
                output=source_output,
                code_build_clone_output=True,
            )
        else:
            self.repo = codecommit.Repository(
                self, "Repo",
                repository_name=repo_name,
                description="Bootstrap repo for my-mlops",
            )
            self.repo_clone_url_http = self.repo.repository_clone_url_http
            source_action = cpactions.CodeCommitSourceAction(
                action_name="CodeCommit",
                repository=self.repo,
                branch=branch,
                output=source_output,
                trigger=cpactions.CodeCommitTrigger.EVENTS, 
            )

        self.pipeline.add_stage(
            stage_name="Source",
            actions=[
                source_action
            ],
        )

        self.pipeline.add_stage(
            stage_name="Build",
            actions=[
                cpactions.CodeBuildAction(
                    action_name="CodeBuild",
                    project=self.project,
                    input=source_output,
                    outputs=[build_output],
                    execute_batch_build=False,
                    combine_batch_build_artifacts=False,
                )
            ],
        )
