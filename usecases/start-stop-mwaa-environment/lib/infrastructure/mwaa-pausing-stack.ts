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

import { CONFIRM_DELETED } from './mwaa-polling-stack';
import {
  DagTriggerStateInput,
  EnvironmentPollerStateInput,
  MwaaPauseResumeBaseStack,
  MwaaPauseResumeStackProps,
} from './mwaa-pause-resume-base-stack';

interface PutObjectStateInput {
  stateName: string;
  bucket: s3.IBucket;
  key: string;
  body: cdk.IResolvable;
}

export class MwaaPausingStack extends MwaaPauseResumeBaseStack {
  readonly stateMachine: sfn.StateMachine;

  constructor(scope: construct.Construct, id: string, props: MwaaPauseResumeStackProps) {
    super(scope, id, props);
    this.stateMachine = this.createStateMachine(props);
    this.createSchedule(props.pauseCronSchedule, props.scheduleTimeZone, this.stateMachine);
  }

  createStateMachine(props: MwaaPauseResumeStackProps): sfn.StateMachine {
    const name = this.getName('pausing-sfn');

    const storeEnvironmentInput: PutObjectStateInput = {
      stateName: 'Store environment details',
      bucket: props.backupBucket!,
      key: props.environmentBackupFile,
      body: sfn.JsonPath.objectAt('$'),
    };

    const dagTriggerInput: DagTriggerStateInput = {
      stateName: 'Export metadata',
      dagName: props.metadataExportDagName,
      bucketName: props.backupBucket!.bucketName,
      dagTriggerFunction: props.dagTriggerFunction!,
    };

    const envPollerInput: EnvironmentPollerStateInput = {
      stateName: 'Confirm environment deletion',
      command: CONFIRM_DELETED,
      stateMachine: props.pollingStateMachine!,
    };

    const successfulFlow = this.createS3PutObjectState(storeEnvironmentInput)
      .next(this.createDagTriggerState(dagTriggerInput))
      .next(this.createDeleteEnvironmentState(props))
      .next(this.creatEnvironmentPollerState(envPollerInput));

    const failedFlow = this.createJobFailedState(
      'MWAA environment not available',
      'The getEnvironment API call returned a not AVAILABLE status'
    );

    const definition = this.createGetEnvironmentState(props).next(
      new sfn.Choice(this, 'Check status')
        .when(sfn.Condition.stringEquals('$.Environment.Status', 'AVAILABLE'), successfulFlow)
        .otherwise(failedFlow)
    );

    const stateMachine = new sfn.StateMachine(this, name, {
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.minutes(props.pauseTimeoutMins),
    });

    return stateMachine;
  }

  createGetEnvironmentState(props: MwaaPauseResumeStackProps): sfn.TaskStateBase {
    const state = new tasks.CallAwsService(this, 'Get environment details', {
      service: 'mwaa',
      action: 'getEnvironment',
      parameters: {
        Name: props.environmentName,
      },
      iamAction: 'airflow:GetEnvironment',
      iamResources: [`arn:aws:airflow:${props.region}:${props.account}:environment/${props.environmentName}`],
    });
    return state;
  }

  createJobFailedState(cause?: string, error?: string): sfn.State {
    return new sfn.Fail(this, 'Pausing unsuccessful', { cause, error });
  }

  createS3PutObjectState(input: PutObjectStateInput): sfn.TaskStateBase {
    const state = new tasks.CallAwsService(this, input.stateName, {
      service: 's3',
      action: 'putObject',
      parameters: {
        Body: input.body,
        Bucket: input.bucket.bucketName,
        Key: input.key,
      },
      iamResources: [input.bucket.arnForObjects(input.key)],
    });
    return state;
  }

  createDeleteEnvironmentState(props: MwaaPauseResumeStackProps): sfn.State {
    const state = new tasks.CallAwsService(this, 'Delete environment', {
      service: 'mwaa',
      action: 'deleteEnvironment',
      parameters: {
        Name: props.environmentName,
      },
      iamAction: 'airflow:DeleteEnvironment',
      iamResources: [`arn:aws:airflow:${props.region}:${props.account}:environment/${props.environmentName}`],
    });
    return state;
  }
}
