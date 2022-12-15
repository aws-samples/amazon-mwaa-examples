#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""This module contains AWS Lambda hook"""
from typing import Any, List, Optional

from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from airflow.exceptions import AirflowException


class LambdaHook(AwsBaseHook):
    """
    Interact with AWS Lambda

    Additional arguments (such as ``aws_conn_id``) may be specified and
    are passed down to the underlying AwsBaseHook.

    .. seealso::
        :class:`~airflow.providers.amazon.aws.hooks.base_aws.AwsBaseHook`

    :param function_name: AWS Lambda Function Name
    :param log_type: Tail Invocation Request
    :param qualifier: AWS Lambda Function Version or Alias Name
    :param invocation_type: AWS Lambda Invocation Type (RequestResponse, Event etc)
    """

    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        kwargs["client_type"] = "lambda"
        super().__init__(*args, **kwargs)

    def invoke_lambda(
        self,
        *,
        function_name: str,
        invocation_type: Optional[str] = None,
        log_type: Optional[str] = None,
        client_context: Optional[str] = None,
        payload: Optional[str] = None,
        qualifier: Optional[str] = None,
    ):
        """Invoke Lambda Function. Refer to the boto3 documentation for more info."""
        invoke_args = {
            "FunctionName": function_name,
            "InvocationType": invocation_type,
            "LogType": log_type,
            "ClientContext": client_context,
            "Payload": payload,
            "Qualifier": qualifier,
        }
        return self.conn.invoke(**{k: v for k, v in invoke_args.items() if v is not None})

    def delete_lambda(
        self,
        *,
        function_name: str,
        qualifier: Optional[str] = None,

    ):
        """Deletes Lambda Function. Refer to the boto3 documentation for more info."""
        delete_func_args = {
            "FunctionName": function_name,
            "Qualifier": qualifier,
        }

        return self.conn.delete_function(
            **{k: v for k, v in delete_func_args.items() if v is not None},
        )

    def get_function_state(
        self,
        *,
        function_name: str,
        qualifier: Optional[str] = None,
    ):
        """Makes a GetFunctionConfiguration call for the arn. Refer to the boto3 documentation for more info."""
        get_func_args = {
            "FunctionName": function_name,
            "Qualifier": qualifier,
        }
        return self.conn.get_function_configuration(
            **{k: v for k, v in get_func_args.items() if v is not None},
        )

    def create_lambda(
        self,
        *,
        function_name: str,
        runtime: Optional[str] = None,
        role: str,
        handler: Optional[str] = None,
        code: dict,
        description: Optional[str] = None,
        timeout: Optional[int] = None,
        memory_size: Optional[int] = None,
        publish: Optional[bool] = None,
        vpc_config: Optional[Any] = None,
        package_type: Optional[str] = None,
        dead_letter_config: Optional[Any] = None,
        environment: Optional[Any] = None,
        kms_key_arn: Optional[str] = None,
        tracing_config: Optional[Any] = None,
        tags: Optional[Any] = None,
        layers: Optional[list] = None,
        file_system_configs: Optional[List[Any]] = None,
        image_config: Optional[Any] = None,
        code_signing_config_arn: Optional[str] = None,
        architectures: Optional[List[str]] = None,
    ) -> dict:
        if (package_type != 'Image'):
            if (handler is None):
                raise AirflowException(
                    'handler parameter is required if the deployment package is a .zip file archive')
            if (runtime is None):
                raise AirflowException(
                    'runtime parameter is required if the deployment package is a .zip file archive')

        """Create a Lambda Function"""
        create_function_args = {
            "FunctionName": function_name,
            "Runtime": runtime,
            "Role": role,
            "Handler": handler,
            "Code": code,
            "Description": description,
            "Timeout": timeout,
            "MemorySize": memory_size,
            "Publish": publish,
            "VpcConfig": vpc_config,
            "PackageType": package_type,
            "DeadLetterConfig": dead_letter_config,
            "Environment": environment,
            "KMSKeyArn": kms_key_arn,
            "TracingConfig": tracing_config,
            "Tags": tags,
            "Layers": layers,
            "FileSystemConfigs": file_system_configs,
            "ImageConfig": image_config,
            "CodeSigningConfigArn": code_signing_config_arn,
            "Architectures": architectures,
        }
        self.log.info("Calling Create Lambda ")
        return self.conn.create_function(
            **{k: v for k, v in create_function_args.items() if v is not None},
        )
