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
import { Capture, Match, Template } from 'aws-cdk-lib/assertions';

import configuration, { Config } from '../../lib/commons/config';
import { MwaaMainStack } from '../../lib/infrastructure/mwaa-main-stack';
import { prepareTestEnvironment } from '../commons/prepare-test-environment';

describe('MwaaCommonStack', () => {
  let config: Config;
  let commonStack: cdk.NestedStack;

  describe('when MWAA_UPDATE_EXECUTION_ROLE is set to yes', () => {
    beforeEach(() => {
      prepareTestEnvironment();
      process.env.MWAA_UPDATE_EXECUTION_ROLE = 'yes';

      config = configuration();
      const app = new cdk.App();
      const mainStack = new MwaaMainStack(app, 'mwaa-main-stack', {
        ...config,
        env: {
          account: config.account,
          region: config.region,
        },
      });
      commonStack = mainStack.commonStack;
    });

    it('should define a backup bucket, source bucket DAG deployment, dag trigger function, source MWAA role change', () => {
      const template = Template.fromStack(commonStack);
      console.log(JSON.stringify(template.toJSON(), null, 2));

      // Backup bucket
      template.resourceCountIs('AWS::S3::Bucket', 1);
      // Source bucket DAG deployment
      template.resourceCountIs('Custom::CDKBucketDeployment', 1);
      // Two lambdas - one for dag trigger and another for bucket deployment
      template.resourceCountIs('AWS::Lambda::Function', 2);

      const rolesCapture = new Capture();
      template.hasResourceProperties(
        'AWS::IAM::Policy',
        Match.objectEquals({
          PolicyDocument: {
            Statement: [
              {
                Action: ['states:SendTaskSuccess', 'states:SendTaskFailure', 'states:SendTaskHeartbeat'],
                Effect: 'Allow',
                Resource: `arn:aws:states:${config.region}:${config.account}:stateMachine:*`,
              },
            ],
            Version: Match.anyValue(),
          },
          PolicyName: Match.anyValue(),
          Roles: [rolesCapture],
        })
      );

      expect(config.executionRoleArn.includes(rolesCapture.asString())).toBeTruthy();
    });
  });

  describe('when MWAA_UPDATE_EXECUTION_ROLE is set to no', () => {
    beforeEach(() => {
      prepareTestEnvironment();
      process.env.MWAA_UPDATE_EXECUTION_ROLE = 'no';

      config = configuration();
      const app = new cdk.App();
      const mainStack = new MwaaMainStack(app, 'mwaa-main-stack', {
        ...config,
        env: {
          account: config.account,
          region: config.region,
        },
      });
      commonStack = mainStack.commonStack;
    });

    it('should define a backup bucket, source bucket DAG deployment, and dag trigger function', () => {
      const template = Template.fromStack(commonStack);
      console.log(JSON.stringify(template.toJSON(), null, 2));

      // Backup bucket
      template.resourceCountIs('AWS::S3::Bucket', 1);
      // Source bucket DAG deployment
      template.resourceCountIs('Custom::CDKBucketDeployment', 1);
      // Two lambdas - one for dag trigger and another for bucket deployment
      template.resourceCountIs('AWS::Lambda::Function', 2);

      // No Policy change
      const policyMatch = Match.objectEquals({
        PolicyDocument: {
          Statement: [
            {
              Action: ['states:SendTaskSuccess', 'states:SendTaskFailure', 'states:SendTaskHeartbeat'],
              Effect: 'Allow',
              Resource: Match.anyValue(),
            },
          ],
          Version: Match.anyValue(),
        },
        PolicyName: Match.anyValue(),
        Roles: [Match.anyValue()],
      });
      template.resourcePropertiesCountIs('AWS::IAM::Policy', policyMatch, 0);
    });
  });
});
