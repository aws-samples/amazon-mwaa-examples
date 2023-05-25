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

import { DagsCli } from './dags-cli';
import { handler } from './dags-trigger-function';

describe('Dags Trigger Function', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  it('should unpause and trigger the supplied dag', async () => {
    const expectedResult = {
      stdOut: 'output',
      stdError: '',
    };

    const unpauseSpy = jest.spyOn(DagsCli.prototype, 'unpauseDag').mockResolvedValue(expectedResult);

    const triggerSpy = jest.spyOn(DagsCli.prototype, 'triggerDag').mockResolvedValue(expectedResult);

    const result = await handler({
      taskToken: 'a-token',
      dag: 'a-dag',
      bucket: 'a-bucket',
    });

    expect(result).toEqual(expectedResult);
    expect(unpauseSpy).toHaveBeenLastCalledWith('a-dag');
    expect(triggerSpy).toHaveBeenLastCalledWith('a-dag', { taskToken: 'a-token', bucket: 'a-bucket' });
  });
});
