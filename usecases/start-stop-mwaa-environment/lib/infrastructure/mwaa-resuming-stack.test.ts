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
import { Template } from 'aws-cdk-lib/assertions';

import configuration, { Config } from '../../lib/commons/config';
import { MwaaMainStack } from '../../lib/infrastructure/mwaa-main-stack';
import { prepareTestEnvironment } from '../commons/prepare-test-environment';

describe('MwaaResumingStack', () => {
  let config: Config;
  let resumingStack: cdk.NestedStack;

  beforeEach(() => {
    prepareTestEnvironment();
    process.env.MWAA_UPDATE_EXECUTION_ROLE = 'yes';

    config = configuration();
    const app = new cdk.App();
    const mainStack = new MwaaMainStack(app, 'mwaa-main-stack', config);
    resumingStack = mainStack.resumingStack;
  });

  it('should define a scheduler, state machine, a new environment function', () => {
    const template = Template.fromStack(resumingStack);

    template.resourceCountIs('AWS::Scheduler::Schedule', 1);
    template.resourceCountIs('AWS::StepFunctions::StateMachine', 1);
    template.resourceCountIs('AWS::Lambda::Function', 1);
  });
});
