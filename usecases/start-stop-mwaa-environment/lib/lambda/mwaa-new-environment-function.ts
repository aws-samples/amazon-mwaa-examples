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

import { CreateEnvironmentCommand, CreateEnvironmentCommandInput, CreateEnvironmentCommandOutput, MWAAClient } from '@aws-sdk/client-mwaa';

const client = new MWAAClient({});

export const handler = async (event: Record<string, CreateEnvironmentCommandInput>): Promise<CreateEnvironmentCommandOutput> => {
  console.info('Create MWAA Environment Event', event);

  const newEnvInput = event.environment;
  sanitizeInput(newEnvInput);

  const createEnvCommand = new CreateEnvironmentCommand(newEnvInput);
  const result = await client.send(createEnvCommand);

  console.info('Create MWAA Environment Result', result);
  return result;
};

function sanitizeInput(input: CreateEnvironmentCommandInput) {
  if (Object.keys(input.Tags || {}).length === 0) {
    input.Tags = undefined;
  }
}
