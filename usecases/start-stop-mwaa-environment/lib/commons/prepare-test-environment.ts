/*
Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
*/

export function prepareTestEnvironment(updateExecutionRole = 'yes') {
  process.env.CDK_DEFAULT_ACCOUNT = '111222333444';
  process.env.CDK_DEFAULT_REGION = 'us-east-1';
  process.env.MWAA_MAIN_STACK_NAME = 'mwaa-main-stack';
  process.env.MWAA_ENV_NAME = 'mwaa-my-env';
  process.env.MWAA_ENV_VERSION = '2.4.3';
  process.env.MWAA_SOURCE_BUCKET_NAME = 'mwaa-my-env-bucket';
  process.env.MWAA_EXECUTION_ROLE_ARN = 'arn:aws:iam::111222333444:role/service-role/mwaa-my-env-1U3X48JADEAC';
  process.env.MWAA_UPDATE_EXECUTION_ROLE = updateExecutionRole;
  process.env.MWAA_PAUSE_CRON_SCHEDULE = '0 20 ? * MON-FRI *';
  process.env.MWAA_RESUME_CRON_SCHEDULE = '0 6 ? * MON-FRI *';
  process.env.MWAA_SCHEDULE_TIME_ZONE = 'America/Indiana/Indianapolis';
}
