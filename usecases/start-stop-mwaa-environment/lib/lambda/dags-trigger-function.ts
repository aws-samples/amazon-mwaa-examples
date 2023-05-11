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

import { DagsCliResult, DagsCli } from './dags-cli';

const envName = process.env.MWAA_ENV_NAME || '';

export const handler = async (event: Record<string, unknown>): Promise<DagsCliResult> => {
  console.info('Event', event);
  const dagsCli = new DagsCli(envName);

  const taskToken = event['taskToken'] as string;
  const dag = event['dag'] as string;
  const bucket = event['bucket'] as string;

  console.info(`Unpausing ${dag} ...`);
  let mwaaResult = await dagsCli.unpauseDag(dag);
  console.info('DAG unpause result:', mwaaResult);

  const config = { taskToken, bucket };
  console.info(`Trigerring DAG ${dag} with config: `, config);
  mwaaResult = await dagsCli.triggerDag(dag, config);
  console.info('DAG trigger result: ', mwaaResult);

  return mwaaResult;
};
