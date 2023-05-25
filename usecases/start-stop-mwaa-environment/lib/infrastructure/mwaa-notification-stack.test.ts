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
import { MwaaNotificationStack } from './mwaa-notification-stack';

describe('MWAANotificationStack', () => {
  let config: Config;
  let mainStack: MwaaMainStack;
  let notificationStack: MwaaNotificationStack | undefined;

  describe('when a notification email is specified', () => {
    beforeEach(() => {
      prepareTestEnvironment();
      process.env.MWAA_UPDATE_EXECUTION_ROLE = 'yes';
      process.env.MWAA_NOTIFICATION_EMAILS = '[abc@example.com]';
      process.env.MWAA_NOTIFICATION_TYPES = '[FAILED]';

      config = configuration();
      const app = new cdk.App();
      mainStack = new MwaaMainStack(app, 'mwaa-main-stack', config);
      notificationStack = mainStack.notificationStack;
    });

    it('should create a notification stack with event a bridge rule, a sns topic, and an email subscription', () => {
      expect(notificationStack).toBeTruthy();

      const template = Template.fromStack(notificationStack!);

      console.log(JSON.stringify(template.toJSON(), null, 2));

      template.resourceCountIs('AWS::SNS::Topic', 1);
      template.resourceCountIs('AWS::SNS::Subscription', 1);
      template.hasResourceProperties('AWS::SNS::Subscription', {
        Protocol: 'email',
        TopicArn: Match.anyValue(),
        Endpoint: 'abc@example.com',
      });

      template.resourceCountIs('AWS::Events::Rule', 1);

      const pausingSMCapture = new Capture();
      const resumingSMCapture = new Capture();
      const targetCapture = new Capture();

      template.hasResourceProperties('AWS::Events::Rule', {
        EventPattern: {
          source: ['aws.states'],
          'detail-type': ['Step Functions Execution Status Change'],
          detail: {
            status: ['FAILED'],
            stateMachineArn: [{ Ref: pausingSMCapture }, { Ref: resumingSMCapture }],
          },
        },
        State: 'ENABLED',
        Targets: targetCapture,
      });

      expect(pausingSMCapture.asString()).toEqual(expect.stringContaining('pausing'));
      expect(resumingSMCapture.asString()).toEqual(expect.stringContaining('resuming'));
      expect(targetCapture.asArray()).toHaveLength(1);
    });
  });

  describe('when several notification emails are specified', () => {
    beforeEach(() => {
      prepareTestEnvironment();
      process.env.MWAA_UPDATE_EXECUTION_ROLE = 'yes';
      process.env.MWAA_NOTIFICATION_EMAILS = '[abc@example.com, def@example.com]';
      process.env.MWAA_NOTIFICATION_TYPES = '[FAILED, SUCCEEDED]';

      config = configuration();
      const app = new cdk.App();
      mainStack = new MwaaMainStack(app, 'mwaa-main-stack', config);
      notificationStack = mainStack.notificationStack;
    });

    it('should create a notification stack with event bridge rule, sns topic, and multiple email subscriptions', () => {
      expect(notificationStack).toBeTruthy();

      const template = Template.fromStack(notificationStack!);

      console.log(JSON.stringify(template.toJSON(), null, 2));

      template.resourceCountIs('AWS::SNS::Topic', 1);
      template.resourceCountIs('AWS::SNS::Subscription', 2);
      template.hasResourceProperties('AWS::SNS::Subscription', {
        Protocol: 'email',
        TopicArn: Match.anyValue(),
        Endpoint: 'abc@example.com',
      });
      template.hasResourceProperties('AWS::SNS::Subscription', {
        Protocol: 'email',
        TopicArn: Match.anyValue(),
        Endpoint: 'def@example.com',
      });

      template.resourceCountIs('AWS::Events::Rule', 1);

      const pausingSMCapture = new Capture();
      const resumingSMCapture = new Capture();
      const targetCapture = new Capture();

      template.hasResourceProperties('AWS::Events::Rule', {
        EventPattern: {
          source: ['aws.states'],
          'detail-type': ['Step Functions Execution Status Change'],
          detail: {
            status: ['FAILED', 'SUCCEEDED'],
            stateMachineArn: [{ Ref: pausingSMCapture }, { Ref: resumingSMCapture }],
          },
        },
        State: 'ENABLED',
        Targets: targetCapture,
      });

      expect(pausingSMCapture.asString()).toEqual(expect.stringContaining('pausing'));
      expect(resumingSMCapture.asString()).toEqual(expect.stringContaining('resuming'));
      expect(targetCapture.asArray()).toHaveLength(1);
    });
  });

  describe('when no notification emails are specified', () => {
    it('should not create the notification stack', () => {
      prepareTestEnvironment();
      process.env.MWAA_UPDATE_EXECUTION_ROLE = 'yes';
      process.env.MWAA_NOTIFICATION_EMAILS = '';

      config = configuration();
      const app = new cdk.App();
      mainStack = new MwaaMainStack(app, 'mwaa-main-stack', config);
      notificationStack = mainStack.notificationStack;
      expect(notificationStack).not.toBeTruthy();
    });
  });

  describe('when an invalid email is specified', () => {
    it('should not create the notification stack', () => {
      prepareTestEnvironment();
      process.env.MWAA_UPDATE_EXECUTION_ROLE = 'yes';
      process.env.MWAA_NOTIFICATION_EMAILS = '[abc@example.com,def@example]';

      config = configuration();
      const app = new cdk.App();

      expect.assertions(1);
      try {
        new MwaaMainStack(app, 'mwaa-main-stack', config);
      } catch (error) {
        expect(error.message).toEqual('Invalid email [def@example] supplied in the MWAA_NOTIFICATION_EMAILS environment variable!');
      }
    });
  });
});
