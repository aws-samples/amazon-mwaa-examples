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
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import { join } from 'path';

import {
  DagTriggerStateInput,
  EnvironmentPollerStateInput,
  MwaaPauseResumeBaseStack,
  MwaaPauseResumeStackProps,
} from './mwaa-pause-resume-base-stack';
import { CONFIRM_CREATED } from './mwaa-polling-stack';

interface GetObjectStateInput {
  stateName: string;
  bucket: s3.IBucket;
  key: string;
}

export class MwaaResumingStack extends MwaaPauseResumeBaseStack {
  readonly newEnvironmentFunction: lambdajs.NodejsFunction;
  readonly updateEnvironmentFunction?: lambdajs.NodejsFunction;
  readonly stateMachine: sfn.StateMachine;

  constructor(scope: construct.Construct, id: string, props: MwaaPauseResumeStackProps) {
    super(scope, id, props);
    this.newEnvironmentFunction = this.createNewEnvironmentFunction(props);
    if (props.updateAfterRestore == 'yes') {
      this.updateEnvironmentFunction = this.createUpdateEnvironmentFunction(props);
    }
    this.stateMachine = this.createStateMachine(props, this.newEnvironmentFunction, this.updateEnvironmentFunction);
    this.createSchedule(props.resumeCronSchedule, props.scheduleTimeZone, this.stateMachine);
  }

  createStateMachine(props: MwaaPauseResumeStackProps, newEnvFunction: lambdajs.NodejsFunction, updateEnvFunction?: lambdajs.NodejsFunction): sfn.StateMachine {
    const name = this.getName('resuming-sfn');

    const retrieveEnvironmentInput: GetObjectStateInput = {
      stateName: 'Retrieve environment details',
      bucket: props.backupBucket!,
      key: props.environmentBackupFile,
    };

    const envPollerInput: EnvironmentPollerStateInput = {
      stateName: 'Confirm environment creation',
      command: CONFIRM_CREATED,
      stateMachine: props.pollingStateMachine!,
    };

    const dagTriggerInput: DagTriggerStateInput = {
      stateName: 'Restore metadata',
      dagName: props.metadataImportDagName,
      bucketName: props.backupBucket!.bucketName,
      dagTriggerFunction: props.dagTriggerFunction!,
    };

    let definition = this.createS3GetObjectState(retrieveEnvironmentInput)
      .next(this.createNewEnvironmentState(newEnvFunction))
      .next(this.creatEnvironmentPollerState(envPollerInput))
      .next(this.createDagTriggerState(dagTriggerInput));

    if (props.updateAfterRestore === 'yes') {
      definition = definition.next(this.createUpdateEnvironmentState(props, updateEnvFunction!));
    }

    const stateMachine = new sfn.StateMachine(this, name, {
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      timeout: cdk.Duration.minutes(props.resumeTimoutMins),
    });

    return stateMachine;
  }

  createS3GetObjectState(input: GetObjectStateInput): sfn.TaskStateBase {
    const state = new tasks.CallAwsService(this, input.stateName, {
      service: 's3',
      action: 'getObject',
      parameters: {
        Bucket: input.bucket.bucketName,
        Key: input.key,
      },
      iamResources: [input.bucket.arnForObjects(input.key)],
      resultSelector: {
        'result.$': 'States.StringToJson($.Body)',
      },
    });
    return state;
  }

  createNewEnvironmentState(newEnvFunc: lambdajs.NodejsFunction): sfn.State {
    const state = new tasks.LambdaInvoke(this, 'Create environment', {
      lambdaFunction: newEnvFunc,
      payload: sfn.TaskInput.fromObject({
        environment: sfn.JsonPath.objectAt('$.result.Environment'),
      }),
    });
    return state;
  }

  createNewEnvironmentFunction(props: MwaaPauseResumeStackProps): lambdajs.NodejsFunction {
    const name = this.getName('new-environment-fn');
    const newEnvironmentFunc = new lambdajs.NodejsFunction(this, name, {
      entry: join(__dirname, '..', 'lambda', 'mwaa-new-environment-function.ts'),
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
        NODE_OPTIONS: '--enable-source-maps',
      },
    });

    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        resources: [`arn:aws:airflow:${props.region}:${props.account}:environment/${props.environmentName}`],
        actions: ['airflow:CreateEnvironment', 'airflow:TagResource'],
      })
    );
    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        resources: [props.sourceBucket!.bucketArn],
        actions: ['s3:GetEncryptionConfiguration'],
      })
    );
    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['logs:CreateLogStream', 'logs:CreateLogGroup', 'logs:DescribeLogGroups'],
        resources: ['arn:aws:logs:*:*:log-group:airflow-*:*'],
      })
    );
    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'ec2:AttachNetworkInterface',
          'ec2:CreateNetworkInterface',
          'ec2:CreateNetworkInterfacePermission',
          'ec2:DescribeDhcpOptions',
          'ec2:DescribeNetworkInterfaces',
          'ec2:DescribeSecurityGroups',
          'ec2:DescribeSubnets',
          'ec2:DescribeVpcEndpoints',
          'ec2:DescribeVpcs',
        ],
        resources: ['*'],
      })
    );
    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['ec2:CreateVpcEndpoint', 'ec2:ModifyVpcEndpoint'],
        resources: [
          'arn:aws:ec2:*:*:vpc/*',
          'arn:aws:ec2:*:*:vpc-endpoint/*',
          'arn:aws:ec2:*:*:security-group/*',
          'arn:aws:ec2:*:*:subnet/*',
        ],
      })
    );
    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['ec2:CreateTags'],
        resources: ['arn:aws:ec2:*:*:vpc-endpoint/*'],
      })
    );
    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],
      })
    );
    newEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['iam:PassRole'],
        resources: ['*'],
      })
    );

    return newEnvironmentFunc;
  }


  createUpdateEnvironmentState(props: MwaaPauseResumeStackProps, updateEnvFunc: lambdajs.NodejsFunction): sfn.State {
    const state = new tasks.LambdaInvoke(this, 'Update environment', {
      lambdaFunction: updateEnvFunc,
      payload: sfn.TaskInput.fromObject({
        Name: props.environmentName
      }),
    });
    return state;
  }

  createUpdateEnvironmentFunction(props: MwaaPauseResumeStackProps): lambdajs.NodejsFunction {
    const name = this.getName('update-environment-fn');
    const updateEnvironmentFunc = new lambdajs.NodejsFunction(this, name, {
      entry: join(__dirname, '..', 'lambda', 'mwaa-update-environment-function.ts'),
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
        NODE_OPTIONS: '--enable-source-maps',
      },
    });

    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        resources: [`arn:aws:airflow:${props.region}:${props.account}:environment/${props.environmentName}`],
        actions: ['airflow:UpdateEnvironment'],
      })
    );
    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        resources: [props.sourceBucket!.bucketArn],
        actions: ['s3:GetEncryptionConfiguration'],
      })
    );
    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['logs:CreateLogStream', 'logs:CreateLogGroup', 'logs:DescribeLogGroups'],
        resources: ['arn:aws:logs:*:*:log-group:airflow-*:*'],
      })
    );
    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          'ec2:AttachNetworkInterface',
          'ec2:CreateNetworkInterface',
          'ec2:CreateNetworkInterfacePermission',
          'ec2:DescribeDhcpOptions',
          'ec2:DescribeNetworkInterfaces',
          'ec2:DescribeSecurityGroups',
          'ec2:DescribeSubnets',
          'ec2:DescribeVpcEndpoints',
          'ec2:DescribeVpcs',
        ],
        resources: ['*'],
      })
    );
    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['ec2:CreateVpcEndpoint', 'ec2:ModifyVpcEndpoint'],
        resources: [
          'arn:aws:ec2:*:*:vpc/*',
          'arn:aws:ec2:*:*:vpc-endpoint/*',
          'arn:aws:ec2:*:*:security-group/*',
          'arn:aws:ec2:*:*:subnet/*',
        ],
      })
    );
    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['ec2:CreateTags'],
        resources: ['arn:aws:ec2:*:*:vpc-endpoint/*'],
      })
    );
    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['cloudwatch:PutMetricData'],
        resources: ['*'],
      })
    );
    updateEnvironmentFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ['iam:PassRole'],
        resources: ['*'],
      })
    );

    return updateEnvironmentFunc;
  }
}
