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

import { mockClient, AwsClientStub } from 'aws-sdk-client-mock';
import 'aws-sdk-client-mock-jest';
import { UpdateEnvironmentCommand, MWAAClient } from '@aws-sdk/client-mwaa';
import { handler } from '../../lib/lambda/mwaa-update-environment-function';

let mwaaMock: AwsClientStub<MWAAClient>;

describe('Update Environment Lambda Function', () => {
  beforeEach(() => {
    mwaaMock = mockClient(MWAAClient);
  });

  afterEach(() => {
    mwaaMock.restore();
  });

  it('should make an API call to update the MWAA environment', async () => {
    mwaaMock.on(UpdateEnvironmentCommand).resolves({ Arn: 'my-env-arn' });

    const result = await handler({ Name: 'my-env' });

    expect(mwaaMock).toHaveReceivedCommand(UpdateEnvironmentCommand);
    expect(result).toEqual({ Arn: 'my-env-arn' });
  });
});
