# Notice

This sample is licensed under MIT-0. See [LICENSE](LICENSE).

## Bundled content

`scripts/build-agent.sh` adds the following third-party content to
`dist/agent.zip`. None of it is stored in this repository. `dist/plugins.zip`
contains only this sample's own code.

### Agent Toolkit for AWS skills

The MWAA skills are copied at build time from
[aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws),
pinned to commit `174379354c7c93f9e80249265f3fffa67a42f0c1` in
[skills.lock](skills.lock). They are licensed under the
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) with this
notice:

```text
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
```

### Python packages

The versions are pinned with hashes in
[agent/requirements.lock](agent/requirements.lock). Licenses are as declared in
each package's metadata. Check the upstream project before you redistribute.

Ruff ships as a compiled binary. The `LICENSE` file in its wheel lists the
licenses of the code it includes.

<!-- markdownlint-disable MD013 -->

| Package                                        | License                    | Source                                                           |
| ---------------------------------------------- | -------------------------- | ---------------------------------------------------------------- |
| annotated-types@0.8.0                          | MIT                        | <https://github.com/annotated-types/annotated-types>             |
| anyio@4.16.0                                   | MIT                        | <https://github.com/agronholm/anyio>                             |
| attrs@26.1.0                                   | MIT                        | <https://github.com/python-attrs/attrs>                          |
| bedrock-agentcore@1.25.3                       | Apache-2.0                 | <https://github.com/aws/bedrock-agentcore-sdk-python>            |
| boto3@1.43.123                                 | Apache-2.0                 | <https://github.com/boto/boto3>                                  |
| botocore@1.43.123                              | Apache-2.0                 | <https://github.com/boto/botocore>                               |
| certifi@2026.10.23                             | MPL-2.0                    | <https://github.com/certifi/python-certifi>                      |
| cffi@2.1.1                                     | MIT-0                      | <https://github.com/python-cffi/cffi>                            |
| click@8.5.0                                    | BSD-3-Clause               | <https://github.com/pallets/click/>                              |
| cryptography@50.0.2                            | Apache-2.0 OR BSD-3-Clause | <https://github.com/pyca/cryptography/>                          |
| docstring_parser@0.18.0                        | MIT                        | <https://github.com/rr-/docstring_parser>                        |
| h11@0.16.0                                     | MIT                        | <https://github.com/python-hyper/h11>                            |
| httpcore@1.0.9                                 | BSD-3-Clause               | <https://github.com/encode/httpcore>                             |
| httpcore2@2.16.0                               | BSD-3-Clause               | <https://github.com/pydantic/httpx2/blob/main/src/httpcore2>     |
| httpx@0.28.1                                   | BSD-3-Clause               | <https://github.com/encode/httpx>                                |
| httpx2@2.16.0                                  | BSD-3-Clause               | <https://github.com/pydantic/httpx2>                             |
| idna@3.20                                      | BSD-3-Clause               | <https://github.com/kjd/idna>                                    |
| jmespath@1.1.0                                 | MIT                        | <https://github.com/jmespath/jmespath.py>                        |
| jsonschema@4.26.0                              | MIT                        | <https://github.com/python-jsonschema/jsonschema>                |
| jsonschema-specifications@2025.9.1             | MIT                        | <https://github.com/python-jsonschema/jsonschema-specifications> |
| mcp@2.3.0                                      | MIT                        | <https://github.com/modelcontextprotocol/python-sdk>             |
| mcp-types@2.3.0                                | MIT                        | <https://github.com/modelcontextprotocol/python-sdk>             |
| opentelemetry-api@1.45.2                       | Apache-2.0                 | <https://github.com/open-telemetry/opentelemetry-python>         |
| opentelemetry-instrumentation@0.66b2           | Apache-2.0                 | <https://github.com/open-telemetry/opentelemetry-python-contrib> |
| opentelemetry-instrumentation-threading@0.66b2 | Apache-2.0                 | <https://github.com/open-telemetry/opentelemetry-python-contrib> |
| opentelemetry-sdk@1.45.2                       | Apache-2.0                 | <https://github.com/open-telemetry/opentelemetry-python>         |
| opentelemetry-semantic-conventions@0.66b2      | Apache-2.0                 | <https://github.com/open-telemetry/opentelemetry-python>         |
| packaging@26.3                                 | Apache-2.0 OR BSD-2-Clause | <https://github.com/pypa/packaging>                              |
| pycparser@3.12                                 | BSD-3-Clause               | <https://github.com/eliben/pycparser>                            |
| pydantic@2.14.2                                | MIT                        | <https://github.com/pydantic/pydantic>                           |
| pydantic_core@2.50.2                           | MIT                        | <https://github.com/pydantic/pydantic/tree/main/pydantic-core>   |
| PyJWT@2.15.1                                   | MIT                        | <https://github.com/jpadilla/pyjwt>                              |
| python-dateutil@2.9.0.post0                    | Apache-2.0 OR BSD-3-Clause | <https://github.com/dateutil/dateutil>                           |
| python-multipart@0.0.33                        | Apache-2.0                 | <https://github.com/Kludex/python-multipart>                     |
| PyYAML@6.0.3                                   | MIT                        | <https://github.com/yaml/pyyaml>                                 |
| referencing@0.37.0                             | MIT                        | <https://github.com/python-jsonschema/referencing>               |
| rpds-py@2026.9.1                               | MIT                        | <https://github.com/crate-py/rpds>                               |
| ruff@0.17.5                                    | MIT                        | <https://github.com/astral-sh/ruff>                              |
| s3transfer@0.19.3                              | Apache-2.0                 | <https://github.com/boto/s3transfer>                             |
| six@1.17.0                                     | MIT                        | <https://github.com/benjaminp/six>                               |
| sse-starlette@3.6.0                            | BSD-3-Clause               | <https://github.com/sysid/sse-starlette>                         |
| starlette@1.10.0                               | BSD-3-Clause               | <https://github.com/Kludex/starlette>                            |
| strands-agents@1.63.0                          | Apache-2.0                 | <https://github.com/strands-agents/harness-sdk>                  |
| tomli@2.5.0                                    | MIT                        | <https://github.com/hukkin/tomli>                                |
| truststore@0.10.5                              | MIT                        | <https://github.com/sethmlarson/truststore>                      |
| typing-inspection@0.4.4                        | MIT                        | <https://github.com/pydantic/typing-inspection>                  |
| typing_extensions@4.16.0                       | PSF-2.0                    | <https://github.com/python/typing_extensions>                    |
| urllib3@2.8.0                                  | MIT                        | <https://github.com/urllib3/urllib3>                             |
| uvicorn@0.54.0                                 | BSD-3-Clause               | <https://github.com/Kludex/uvicorn>                              |
| watchdog@6.0.0                                 | Apache-2.0                 | <https://github.com/gorakhargosh/watchdog/>                      |
| websockets@17.4                                | BSD-3-Clause               | <https://github.com/python-websockets/websockets>                |
| wrapt@2.5.2                                    | BSD-2-Clause               | <https://github.com/GrahamDumpleton/wrapt>                       |

<!-- markdownlint-enable MD013 -->
