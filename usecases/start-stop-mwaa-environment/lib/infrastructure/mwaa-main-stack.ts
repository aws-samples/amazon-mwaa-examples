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
import * as ec2 from 'aws-cdk-lib/aws-ec2';

import { MwaaCommonStack, MwaaCommonStackProps } from './mwaa-common-stack';
import { MwaaPollingStack, MwaaPollingStackProps } from './mwaa-polling-stack';
import { MwaaPauseResumeStackProps } from './mwaa-pause-resume-base-stack';
import { MwaaPausingStack } from './mwaa-pausing-stack';
import { MwaaResumingStack } from './mwaa-resuming-stack';
import { MwaaNotificationProps, MwaaNotificationStack } from './mwaa-notification-stack';

export interface MwaaStackNameProps {
  mainStackName: string;
  vpcId: string;
  subnetIds: string[];
  securityGroups: string[];
}

export interface MwaaVpc {
  readonly vpc?: ec2.IVpc;
  readonly vpcSubnets?: ec2.SubnetSelection;
  readonly securityGroups?: ec2.ISecurityGroup[];
  readonly vpce?: ec2.InterfaceVpcEndpoint;
}

export type MwaaMainStackProps = MwaaStackNameProps &
  MwaaPollingStackProps &
  MwaaCommonStackProps &
  MwaaPauseResumeStackProps &
  MwaaNotificationProps;

export class MwaaMainStack extends cdk.Stack {
  readonly mwaaVpc: MwaaVpc;
  readonly commonStack: MwaaCommonStack;
  readonly pollingStack: MwaaPollingStack;
  readonly pausingStack: MwaaPausingStack;
  readonly resumingStack: MwaaResumingStack;
  readonly notificationStack?: MwaaNotificationStack;

  constructor(scope: construct.Construct, id: string, props: MwaaMainStackProps) {
    super(scope, id, props);

    this.mwaaVpc = this.lookupVpc(props);
    props.mwaaVpc = this.mwaaVpc;

    this.commonStack = this.createCommonStack(props);
    props.sourceBucket = this.commonStack.sourceBucket;
    props.backupBucket = this.commonStack.backupBucket;
    props.dagTriggerFunction = this.commonStack.dagTriggerFunction;

    this.pollingStack = this.createPollingStack(props);
    props.pollingStateMachine = this.pollingStack.stateMachine;

    this.pausingStack = this.createPausingStack(props);
    props.pausingStateMachine = this.pausingStack.stateMachine;

    this.resumingStack = this.createResumingStack(props);
    props.resumingStateMachine = this.resumingStack.stateMachine;

    this.notificationStack = this.createNotificationStack(props);
  }

  lookupVpc(props: MwaaMainStackProps): MwaaVpc {
    if (props.vpcId) {
      const vpc = ec2.Vpc.fromLookup(this, `${props.mainStackName}-external-vpc`, {
        vpcId: props.vpcId,
      });

      const subnets = props.subnetIds.map((id) => ec2.Subnet.fromSubnetId(this, id, id));
      const vpcSubnets = { subnets };

      const securityGroups = props.securityGroups.map((sg) => ec2.SecurityGroup.fromSecurityGroupId(this, sg, sg));

      const vpce = vpc.addInterfaceEndpoint(`${props.mainStackName}-sf-vpce`, {
        service: ec2.InterfaceVpcEndpointAwsService.STEP_FUNCTIONS,
        subnets: vpcSubnets,
        securityGroups: securityGroups,
      });

      return { vpc, vpcSubnets, securityGroups, vpce };
    }

    return {};
  }

  createCommonStack(props: MwaaMainStackProps): MwaaCommonStack {
    const commonStackName = 'mwaa-common-stack';
    const commonStack = new MwaaCommonStack(this, commonStackName, {
      ...props,
      stackName: commonStackName,
    });
    return commonStack;
  }

  createPollingStack(props: MwaaMainStackProps): MwaaPollingStack {
    const stackName = 'mwaa-polling-stack';
    const stack = new MwaaPollingStack(this, stackName, {
      ...props,
      stackName: stackName,
    });
    return stack;
  }

  createPausingStack(props: MwaaMainStackProps): MwaaPausingStack {
    const stackName = 'mwaa-pausing-stack';
    const stack = new MwaaPausingStack(this, stackName, {
      ...props,
      stackName: stackName,
    });
    return stack;
  }

  createResumingStack(props: MwaaMainStackProps): MwaaResumingStack {
    const stackName = 'mwaa-resuming-stack';
    const stack = new MwaaResumingStack(this, stackName, {
      ...props,
      stackName: stackName,
    });
    return stack;
  }

  createNotificationStack(props: MwaaMainStackProps): MwaaNotificationStack | undefined {
    if (props.emails.length == 0) {
      return undefined;
    }

    const stackName = 'mwaa-notification-stack';
    const stack = new MwaaNotificationStack(this, stackName, {
      ...props,
      stackName: stackName,
    });
    return stack;
  }
}
