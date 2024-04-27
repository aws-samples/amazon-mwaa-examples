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
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdajs from 'aws-cdk-lib/aws-lambda-nodejs';
import * as iam from 'aws-cdk-lib/aws-iam';
import { join } from 'path';

import { MwaaBaseStack } from './mwaa-base-stack';

export const CONFIRM_DELETED = 'checkDeleted';
export const CONFIRM_CREATED = 'checkCreated';

export interface MwaaPollingStackProps extends cdk.StackProps {
  account: string;
  region: string;
  environmentName: string;
  pollTimeoutMins: number;
  pollFrequencySeconds: number;
}

export class MwaaPollingStack extends MwaaBaseStack {
  readonly stateMachine: sfn.StateMachine;
  readonly pollerFunction: lambdajs.NodejsFunction;

  constructor(scope: construct.Construct, id: string, props: MwaaPollingStackProps) {
    super(scope, id, props);
    this.pollerFunction = this.createPollerFunction(props);
    this.stateMachine = this.createStateMachine(props, this.pollerFunction);
  }

  createPollerFunction(props: MwaaPollingStackProps): lambdajs.NodejsFunction {
    const name = this.getName('polling-fn');
    const pollerFunc = new lambdajs.NodejsFunction(this, name, {
      entry: join(__dirname, '..', 'lambda', 'mwaa-status-poller-function.ts'),
      depsLockFilePath: join(__dirname, '..', 'lambda', 'package-lock.json'),
      runtime: lambda.Runtime.NODEJS_18_X,
      handler: 'handler',
      bundling: {
        sourceMap: true,
        target: 'ES2021',
        format: lambdajs.OutputFormat.CJS,
        mainFields: ['module', 'main'],
      },
      timeout: cdk.Duration.minutes(10),
      environment: {
        MWAA_ENV_NAME: props.environmentName,
        NODE_OPTIONS: '--enable-source-maps',
      },
    });

    pollerFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        resources: [`arn:aws:airflow:${props.region}:${props.account}:environment/${props.environmentName}`],
        actions: ['airflow:GetEnvironment'],
      })
    );
    return pollerFunc;
  }

  createStateMachine(props: MwaaPollingStackProps, pollerFunction: lambdajs.NodejsFunction): sfn.StateMachine {
    const name = this.getName('poller-sfn');

    const waitState = this.createWaitState(props);
    const successState = this.createSuccessState(props);
    const statusCheckState = this.createStatusCheckState(waitState, successState);
    const pollerState = this.createPollingState(pollerFunction);

    const definition = waitState.next(pollerState).next(statusCheckState);

    const stateMachine = new sfn.StateMachine(this, name, {
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.minutes(props.pollTimeoutMins),
    });

    return stateMachine;
  }

  createPollingState(pollerFunction: lambdajs.NodejsFunction): tasks.LambdaInvoke {
    const state = new tasks.LambdaInvoke(this, 'GetStatus', {
      lambdaFunction: pollerFunction,
      payload: sfn.TaskInput.fromObject({
        'command.$': '$$.Execution.Input.command',
      }),
      outputPath: '$.Payload',
    });
    return state;
  }

  createWaitState(props: MwaaPollingStackProps): sfn.Wait {
    const state = new sfn.Wait(this, 'Wait', {
      time: sfn.WaitTime.duration(cdk.Duration.seconds(props.pollFrequencySeconds)),
    });
    return state;
  }

  createSuccessState(props: MwaaPollingStackProps): sfn.State {
    const state = new tasks.CallAwsService(this, 'SuccessNotification', {
      service: 'sfn',
      action: 'sendTaskSuccess',
      parameters: {
        Output: {
          'command.$': '$$.Execution.Input.command',
          status: 'Success',
        },
        'TaskToken.$': '$$.Execution.Input.taskToken',
      },
      iamAction: 'states:SendTaskSuccess',
      iamResources: [`arn:aws:states:${props.region}:${props.account}:stateMachine:*`],
    });
    return state;
  }

  createStatusCheckState(waitState: sfn.Wait, successState: sfn.Succeed): sfn.Choice {
    const state = new sfn.Choice(this, 'CheckStatus')
      .when(sfn.Condition.booleanEquals('$.complete', true), successState)
      .otherwise(waitState);
    return state;
  }
}
