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

export interface MwaaPollingResult {
  complete: boolean;
}

export const COMPLETE: MwaaPollingResult = { complete: true };
export const INCOMPLETE: MwaaPollingResult = { complete: false };

export class MwaaStatusPoller {
  constructor(private environmentName: string, private client = new mwaa.MWAAClient({})) {}

  async checkCreated(): Promise<MwaaPollingResult> {
    const getEnvCommand = new mwaa.GetEnvironmentCommand({ Name: this.environmentName });

    try {
      const result = await this.client.send(getEnvCommand);
      if (result.Environment?.Status === 'AVAILABLE') {
        return COMPLETE;
      }
    } catch (error) {
      const awsError = error as Record<string, string>;
      if (awsError.name !== 'ResourceNotFoundException') {
        throw error;
      }
    }
    return INCOMPLETE;
  }

  async checkDeleted(): Promise<MwaaPollingResult> {
    const getEnvCommand = new mwaa.GetEnvironmentCommand({ Name: this.environmentName });

    try {
      const result = await this.client.send(getEnvCommand);
      if (result.Environment?.Status === 'DELETED') {
        return COMPLETE;
      }
    } catch (error) {
      const awsError = error as Record<string, string>;
      if (awsError.name === 'ResourceNotFoundException') {
        return COMPLETE;
      }
      throw error;
    }
    return INCOMPLETE;
  }
}
