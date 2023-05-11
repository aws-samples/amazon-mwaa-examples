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
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';

import { MwaaBaseStack } from './mwaa-base-stack';

export interface MwaaNotificationProps extends cdk.StackProps {
  emails: string[];
  notificationTypes: string[];
  pausingStateMachine?: sfn.StateMachine;
  resumingStateMachine?: sfn.StateMachine;
}

export class MwaaNotificationStack extends MwaaBaseStack {
  readonly topic: sns.Topic;
  readonly eventRule: events.Rule;

  constructor(scope: construct.Construct, id: string, props: MwaaNotificationProps) {
    super(scope, id, props);
    this.topic = this.createSnsEmailTopic(props);
    this.eventRule = this.setupNotification(props, this.topic);
  }

  createSnsEmailTopic(props: MwaaNotificationProps): sns.Topic {
    this.checkEmails(props.emails);

    const topic = new sns.Topic(this, this.getName('sns'));
    props.emails.forEach((email) => {
      const subscription = new subscriptions.EmailSubscription(email);
      topic.addSubscription(subscription);
    });
    return topic;
  }

  setupNotification(props: MwaaNotificationProps, topic: sns.Topic): events.Rule {
    const rule = new events.Rule(this, this.getName('rule'), {
      eventPattern: {
        source: ['aws.states'],
        detailType: ['Step Functions Execution Status Change'],
        detail: {
          status: props.notificationTypes,
          stateMachineArn: [props.pausingStateMachine!.stateMachineArn, props.resumingStateMachine!.stateMachineArn],
        },
      },
      targets: [new targets.SnsTopic(topic)],
    });
    return rule;
  }

  checkEmails(emails: string[]) {
    const emailRegex = new RegExp(
      /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/
    );
    emails.forEach((email) => {
      if (!emailRegex.test(email)) {
        throw new Error(`Invalid email [${email}] supplied in the MWAA_NOTIFICATION_EMAILS environment variable!`);
      }
    });
  }
}
