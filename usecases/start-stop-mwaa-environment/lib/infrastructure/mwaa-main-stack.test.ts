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

import configuration from '../../lib/commons/config';
import { MwaaMainStack } from '../../lib/infrastructure/mwaa-main-stack';
import { prepareTestEnvironment } from '../commons/prepare-test-environment';

describe('MwaaMainStack', () => {
  beforeEach(() => {
    prepareTestEnvironment();
  });

  it('should compose the common, polling, pausing, and resuming nested stacks', () => {
    const config = configuration();

    const app = new cdk.App();
    const mainStack = new MwaaMainStack(app, 'mwaa-main-stack', {
      ...config,
      env: {
        account: config.account,
        region: config.region,
      },
    });
    const commonStack = mainStack.commonStack;
    const pollingStack = mainStack.pollingStack;
    const pausingStack = mainStack.pausingStack;
    const resumingStack = mainStack.resumingStack;

    expect(commonStack).toBeTruthy();
    expect(pollingStack).toBeTruthy();
    expect(pausingStack).toBeTruthy();
    expect(resumingStack).toBeTruthy();
  });
});
