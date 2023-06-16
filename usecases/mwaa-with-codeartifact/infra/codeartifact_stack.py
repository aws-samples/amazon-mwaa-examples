from aws_cdk import Resource, Stack
import aws_cdk.aws_codeartifact as codeartifact
from constructs import Construct


class CodeArtifactStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        ca_domain = codeartifact.CfnDomain(
            self, "mwaa_codeartifact_domain", domain_name="mwaa"
        )
        self._repo = codeartifact.CfnRepository(
            self,
            "mwaa_codeartifact_repo",
            domain_name=ca_domain.domain_name,
            repository_name="mwaa_repo",
            external_connections=["public:pypi"],
            description="This is demo repo for MWAA.",
        )
        self._repo.add_depends_on(ca_domain)

    @property
    def repo(self) -> Resource:
        return self._repo
