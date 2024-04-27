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

import * as cdk from 'aws-cdk-lib';
import * as construct from 'constructs';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambdajs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as scheduler from 'aws-cdk-lib/aws-scheduler';

import { MwaaBaseStack } from './mwaa-base-stack';

export interface MwaaPauseResumeStackProps extends cdk.StackProps {
  account: string;
  region: string;
  environmentName: string;
  pauseCronSchedule: string;
  resumeCronSchedule: string;
  scheduleTimeZone: string;
  environmentBackupFile: string;
  metadataExportDagName: string;
  metadataImportDagName: string;
  executionRoleArn: string;
  pauseTimeoutMins: number;
  resumeTimoutMins: number;
  sourceBucket?: s3.IBucket;
  backupBucket?: s3.IBucket;
  pollingStateMachine?: sfn.StateMachine;
  dagTriggerFunction?: lambdajs.NodejsFunction;
  updateAfterRestore: string;
}

export interface DagTriggerStateInput {
  stateName: string;
  dagName: string;
  bucketName: string;
  dagTriggerFunction: lambdajs.NodejsFunction;
}

export interface EnvironmentPollerStateInput {
  stateName: string;
  command: string;
  stateMachine: sfn.StateMachine;
}

export abstract class MwaaPauseResumeBaseStack extends MwaaBaseStack {
  constructor(scope: construct.Construct, id: string, props: MwaaPauseResumeStackProps) {
    super(scope, id, props);
  }

  createSchedule(cron: string, timeZone: string, stateMachine: sfn.StateMachine): scheduler.CfnSchedule {
    const role = new iam.Role(this, this.getName('scheduler-role'), {
      assumedBy: new iam.ServicePrincipal('scheduler.amazonaws.com'),
      inlinePolicies: {
        'sfn-start-execution': new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ['states:StartExecution'],
              resources: [stateMachine.stateMachineArn],
            }),
          ],
        }),
      },
    });

    const schedule = new scheduler.CfnSchedule(this, this.getName('schedule'), {
      flexibleTimeWindow: { mode: 'OFF' },
      scheduleExpression: `cron(${cron})`,
      scheduleExpressionTimezone: timeZone,
      target: {
        arn: stateMachine.stateMachineArn,
        roleArn: role.roleArn,
      },
    });
    return schedule;
  }

  createDagTriggerState(input: DagTriggerStateInput): sfn.State {
    const state = new tasks.LambdaInvoke(this, input.stateName, {
      lambdaFunction: input.dagTriggerFunction,
      integrationPattern: sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
      payload: sfn.TaskInput.fromObject({
        taskToken: sfn.JsonPath.taskToken,
        dag: input.dagName,
        bucket: input.bucketName,
      }),
      retryOnServiceExceptions: true,
    });
    return state;
  }

  creatEnvironmentPollerState(input: EnvironmentPollerStateInput): sfn.State {
    const state = new tasks.StepFunctionsStartExecution(this, input.stateName, {
      stateMachine: input.stateMachine,
      integrationPattern: sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
      input: sfn.TaskInput.fromObject({
        taskToken: sfn.JsonPath.taskToken,
        command: input.command,
      }),
    });
    return state;
  }
}
