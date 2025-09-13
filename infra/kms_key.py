import re
from constructs import Construct
from aws_cdk import (
    aws_kms as kms,
    Duration,
    Names, Stack
)

_ALLOWED = re.compile(r"[^a-zA-Z0-9:/_-]+")


def _sanitize_alias(name: str) -> str:
    if not name.startswith("alias/"):
        name = f"alias/{name}"
    name = _ALLOWED.sub("-", name)
    name = re.sub(r"-{2,}", "-", name)
    return name[:256]

class BaseKms(Construct):
    def __init__(self, scope: Construct, construct_id: str, *, alias: str) -> None:
        super().__init__(scope, construct_id)

        self.key = kms.Key(
            self, "Key",
            enable_key_rotation=True,
            pending_window=Duration.days(7),
            description="S3/KMS general-purpose key"
        )

        safe_alias = _sanitize_alias(alias)

        if safe_alias == "alias/":
            uid = Names.unique_id(self)[:8] 
            safe_alias = f"alias/{uid}-kms"

        kms.Alias(
            self, "KeyAlias",
            alias_name=safe_alias,
            target_key=self.key
        )
