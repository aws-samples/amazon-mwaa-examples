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

import * as mwaa from '@aws-sdk/client-mwaa';
import axios from 'axios';

export interface DagsCliResult {
  stdError: string;
  stdOut: string;
}

export class DagsCli {
  protected token: mwaa.CreateCliTokenCommandOutput;

  constructor(private environmentName: string, private environmentVersion: string, private client = new mwaa.MWAAClient({})) {}

  async setup(): Promise<mwaa.CreateCliTokenCommandOutput> {
    if (!this.environmentName) {
      throw new Error('The DagsCli is missing MWAA environment name');
    }

    if (!this.token) {
      const createCliToken = new mwaa.CreateCliTokenCommand({ Name: this.environmentName });
      this.token = await this.client.send(createCliToken);
    }

    return this.token;
  }

  async unpauseDag(dagName: string): Promise<DagsCliResult> {
    const unpauseResult = await this.execute(`dags unpause ${dagName}`);
    if (!unpauseResult.stdOut.includes('paused: False')) {
      throw new Error(`Dag [${dagName}] unpause failed with the following error: ${JSON.stringify(unpauseResult)}`);
    }
    return unpauseResult;
  }

  async triggerDag(dagName: string, configuration?: Record<string, string>): Promise<DagsCliResult> {
    const semVer = this.environmentVersion.split('.');

    let command = '';
    let resultIncludes = '';
    if (+semVer[0] <= 2 && +semVer[1] <= 5) {
      command = `dags trigger ${dagName}`;
      resultIncludes = 'triggered: True';
    } else {
      command = `dags trigger -o json ${dagName}`;
      resultIncludes = '"external_trigger": "True"';
    }

    const triggerResult = await this.execute(command, configuration);
    if (!triggerResult.stdOut.includes(resultIncludes)) {
      throw new Error(`Dag [${dagName}] trigger failed with the following error: ${JSON.stringify(triggerResult)}`);
    }
    return triggerResult;
  }

  async execute(command: string, configuration?: Record<string, string>): Promise<DagsCliResult> {
    const conf = configuration ? ` --conf '${JSON.stringify(configuration)}'` : '';
    const commandPayload = `${command}${conf}`;

    const token = await this.setup();

    const url = `https://${token.WebServerHostname}/aws_mwaa/cli`;
    const headers = {
      Authorization: `Bearer ${this.token.CliToken}`,
      'Content-Type': 'text/plain',
    };
    const result = await axios.post(url, commandPayload, { headers });

    console.log(result);

    const stdError = Buffer.from(result.data.stderr || '', 'base64').toString();
    const stdOut = Buffer.from(result.data.stdout || '', 'base64').toString();

    if (!stdOut) {
      throw Error(`The ${command} failed to execute with the following error: ${stdError}`);
    }
    return { stdOut, stdError };
  }
}
