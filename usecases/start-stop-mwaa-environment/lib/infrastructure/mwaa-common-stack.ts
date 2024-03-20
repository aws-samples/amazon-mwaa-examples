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
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deployment from 'aws-cdk-lib/aws-s3-deployment';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as lambdajs from 'aws-cdk-lib/aws-lambda-nodejs';
import { join } from 'path';

import { MwaaBaseStack } from './mwaa-base-stack';
import { MwaaVpc } from './mwaa-main-stack';

export interface MwaaCommonStackProps extends cdk.StackProps {
  account: string;
  region: string;
  environmentName: string;
  sourceBucketName: string;
  dagsS3Path: string;
  executionRoleArn: string;
  mwaaResources: string;
  updateExecutionRole: string;
  environmentVersion: string;
  mwaaVpc?: MwaaVpc;
}

export class MwaaCommonStack extends MwaaBaseStack {
  readonly sourceBucket: s3.IBucket;
  readonly backupBucket: s3.IBucket;
  readonly dagTriggerFunction: lambdajs.NodejsFunction;
  readonly serviceRole: iam.IRole;

  constructor(scope: construct.Construct, id: string, props: MwaaCommonStackProps) {
    super(scope, id, props);

    this.serviceRole = this.createMWaaExecutionRoleRef(props);
    this.backupBucket = this.createBackupBucket(this.serviceRole);
    this.sourceBucket = this.setupSourceBucket(props);

    this.dagTriggerFunction = this.createDagTriggerFunction(props);
    this.updateExecutionRole(props, this.serviceRole);
  }

  createMWaaExecutionRoleRef(props: MwaaCommonStackProps): iam.IRole {
    const serviceRole = iam.Role.fromRoleArn(this, this.getName('exec-role'), props.executionRoleArn);
    return serviceRole;
  }

  setupSourceBucket(props: MwaaCommonStackProps): s3.IBucket {
    const id = this.getName('source-bucket');
    const bucket = s3.Bucket.fromBucketName(this, id, props.sourceBucketName);

    new s3deployment.BucketDeployment(this, this.getName('dags-deployment'), {
      sources: [s3deployment.Source.asset(`${props.mwaaResources}/assets/dags/${props.environmentVersion}`)],
      destinationBucket: bucket,
      destinationKeyPrefix: props.dagsS3Path,
      prune: false,
    });

    return bucket;
  }

  createBackupBucket(serviceRole: iam.IRole): s3.IBucket {
    const name = this.getName('backup-bucket');
    const bucket = new s3.Bucket(this, name, {
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    bucket.addToResourcePolicy(
      new iam.PolicyStatement({
        principals: [serviceRole],
        effect: iam.Effect.ALLOW,
        actions: [
          's3:Abort*',
          's3:DeleteObject*',
          's3:GetBucket*',
          's3:GetObject*',
          's3:List*',
          's3:PutObject',
          's3:PutObjectLegalHold',
          's3:PutObjectRetention',
          's3:PutObjectTagging',
          's3:PutObjectVersionTagging',
        ],
        resources: [bucket.bucketArn, bucket.arnForObjects('*')],
      })
    );

    new cdk.CfnOutput(this, 'MWAA-Backup-Bucket-Name', { value: bucket.bucketName });
    return bucket;
  }

  createDagTriggerFunction(props: MwaaCommonStackProps): lambdajs.NodejsFunction {
    const name = this.getName('dag-trigger-fn');
    const triggerFunc = new lambdajs.NodejsFunction(this, name, {
      entry: join(__dirname, '..', 'lambda', 'dags-trigger-function.ts'),
      depsLockFilePath: join(__dirname, '..', 'lambda', 'package-lock.json'),
      runtime: lambda.Runtime.NODEJS_18_X,
      handler: 'handler',
      bundling: {
        sourceMap: true,
        target: 'ES2021',
        format: lambdajs.OutputFormat.CJS,
        mainFields: ['module', 'main'],
      },
      ...props.mwaaVpc,
      timeout: cdk.Duration.minutes(10),
      environment: {
        MWAA_ENV_NAME: props.environmentName,
        MWAA_ENV_VERSION: props.environmentVersion,
        NODE_OPTIONS: '--enable-source-maps',
      },
    });

    triggerFunc.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        resources: [`arn:aws:airflow:${props.region}:${props.account}:environment/${props.environmentName}`],
        actions: ['airflow:CreateCliToken'],
      })
    );
    return triggerFunc;
  }

  updateExecutionRole(props: MwaaCommonStackProps, serviceRole: iam.IRole) {
    if (props.updateExecutionRole.toLowerCase() === 'yes') {
      new iam.Policy(this, this.getName('task-token-policy'), {
        roles: [serviceRole],
        statements: [
          new iam.PolicyStatement({
            actions: ['states:SendTaskSuccess', 'states:SendTaskFailure', 'states:SendTaskHeartbeat'],
            effect: iam.Effect.ALLOW,
            resources: [`arn:aws:states:${props.region}:${props.account}:stateMachine:*`],
          }),
        ],
      });
    }
  }
}
