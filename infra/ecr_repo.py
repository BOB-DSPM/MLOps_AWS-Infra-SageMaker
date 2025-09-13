from constructs import Construct
from aws_cdk import (
    aws_ecr as ecr,
    RemovalPolicy,
    Duration,
)

class BaseEcr(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, name: str, keep_untagged: int) -> None:
        super().__init__(scope, construct_id)

        self.repo = ecr.Repository(
            self, "Repository",
            repository_name=name,
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        
        if keep_untagged and keep_untagged > 0:
            self.repo.add_lifecycle_rule(
                description=f"Keep the last {keep_untagged} untagged images",
                tag_status=ecr.TagStatus.UNTAGGED,
                max_image_count=keep_untagged,
            )
        else:
            self.repo.add_lifecycle_rule(
                description="Expire old untagged images",
                tag_status=ecr.TagStatus.UNTAGGED,
                max_image_age=Duration.days(14),
            )