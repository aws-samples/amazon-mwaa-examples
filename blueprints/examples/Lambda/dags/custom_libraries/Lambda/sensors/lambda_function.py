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
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

from botocore.exceptions import ClientError

from airflow import AirflowException
from custom_libraries.Lambda.hooks.lambda_function import LambdaHook
from airflow.sensors.base import BaseSensorOperator

if TYPE_CHECKING:
    from airflow.utils.context import Context


class LambdaStateSensor(BaseSensorOperator):
    """
    Waits for Lambda function to be in Active state.

    .. seealso::
        For more information on how to use this sensor, take a look at the guide:
        :ref:`howto/sensor:LambdaStateSensor`

    :param function_name: function_name to check the state of
    :param aws_conn_id: aws connection to use, defaults to 'aws_default'
    """

    template_fields: Sequence[str] = ('function_name', 'qualifier')

    ACTIVE_STATE = ('Active',)

    FAILED_STATE = ('Failed')

    PENDING_STATE = ('Pending')

    def __init__(
        self,
        *,
        function_name: str,
        qualifier: str,
        aws_conn_id: str = 'aws_default',
        region_name: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.function_name = function_name
        self.qualifier = qualifier
        self.aws_conn_id = aws_conn_id
        self.region_name = region_name
        self.hook: Optional[LambdaHook] = None

    def poke(self, context: Context):
        self.log.info(
            'Poking for statuses : %s:%s', self.function_name, self.qualifier
        )
        function_output = self.get_hook().get_function_state(function_name=self.function_name,
                                                             qualifier=self.qualifier)
        self.log.info('Function output : %s', function_output)
        function_state = function_output['State']

        if function_state in self.FAILED_STATE:
            raise AirflowException(f'Lambda Function creation sensor failed.')

        if function_state in self.PENDING_STATE:
            return False

        return True

    def get_hook(self) -> LambdaHook:
        """Create and return a LambdaHook"""
        if self.hook:
            return self.hook

        self.hook = LambdaHook(aws_conn_id=self.aws_conn_id,
                               region_name=self.region_name)
        return self.hook


__all__ = [
    "LambdaStateSensor"
]
