import aws_cdk as cdk
from aws_cdk import aws_codeartifact as codeartifact
from constructs import Construct


class CodeArtifactStack(cdk.Stack):
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
        self._repo.add_dependency(ca_domain)

    @property
    def repo(self) -> cdk.CfnResource:
        return self._repo