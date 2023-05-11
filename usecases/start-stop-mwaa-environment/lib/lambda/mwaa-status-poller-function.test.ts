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

import { COMPLETE, MwaaStatusPoller } from '../../lib/lambda/mwaa-status-poller';
import { handler } from '../../lib/lambda/mwaa-status-poller-function';

describe('Status Poller Lambda Function', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  it('should call checkCreated API for checkCreated event payload', async () => {
    jest.spyOn(MwaaStatusPoller.prototype, 'checkCreated').mockImplementation(async () => COMPLETE);

    const result = await handler({ command: 'checkCreated' });
    expect(result).toEqual(COMPLETE);
  });

  it('should call checkDeleted API for checkDeleted event payload', async () => {
    jest.spyOn(MwaaStatusPoller.prototype, 'checkDeleted').mockImplementation(async () => COMPLETE);

    const result = await handler({ command: 'checkDeleted' });
    expect(result).toEqual(COMPLETE);
  });

  it('should throw for unknown event payload', async () => {
    expect.assertions(1);

    try {
      await handler({ command: 'checkRandom' });
    } catch (error) {
      expect(error.message).toEqual('Unsupported polling command [checkRandom]!');
    }
  });
});
