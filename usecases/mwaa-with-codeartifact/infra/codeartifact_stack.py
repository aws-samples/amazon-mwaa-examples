from aws_cdk import core
import aws_cdk.aws_codeartifact as codeartifact


class CodeArtifactStack(core.Stack):
    def __init__(self, scope: core.Construct, id: str, **kwargs) -> None:
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
    def repo(self) -> core.Resource:
        return self._repo
