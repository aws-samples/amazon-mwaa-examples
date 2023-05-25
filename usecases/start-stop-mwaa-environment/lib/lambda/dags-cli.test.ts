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
import { CreateCliTokenCommand, MWAAClient } from '@aws-sdk/client-mwaa';
import { DagsCli } from './dags-cli';
import nock from 'nock';

let mwaaMock: AwsClientStub<MWAAClient>;

describe('DagsCli', () => {
  describe('Construction', () => {
    it('should set environmentName and mwaa sdk client', () => {
      const client = new MWAAClient({});
      const cli = new DagsCli('my-env', client);
      expect(cli['environmentName']).toEqual('my-env');
      expect(cli['client']).toBe(client);
    });

    it('should set up default mwaa sdk client if missing', () => {
      const cli = new DagsCli('my-env');
      expect(cli['environmentName']).toEqual('my-env');
      expect(cli['client']).toBeTruthy();
    });
  });

  describe('Methods Needing CLI Token', () => {
    const token = {
      CliToken: 'a-token',
      WebServerHostname: 'mwaa.com',
    };

    beforeEach(() => {
      mwaaMock = mockClient(MWAAClient);
      mwaaMock.on(CreateCliTokenCommand).resolves(token);
    });

    afterEach(() => {
      mwaaMock.restore();
    });

    describe('setup', () => {
      it('should fail if the environment name is missing', async () => {
        const cli = new DagsCli('');

        expect.assertions(1);

        try {
          await cli.setup();
        } catch (error) {
          expect(error.message).toEqual('The DagsCli is missing MWAA environment name');
        }
      });

      it('should get the cli token if not cached', async () => {
        const cli = new DagsCli('my-env');
        const result = await cli.setup();

        expect(result).toEqual(token);
        expect(mwaaMock).toHaveReceivedCommand(CreateCliTokenCommand);
      });

      it('should use the cached cli token if available', async () => {
        const cli = new DagsCli('my-env');
        const result1 = await cli.setup();
        const result2 = await cli.setup();

        expect(result1).toEqual(token);
        expect(result1).toBe(result2);
        expect(mwaaMock).toHaveReceivedCommandTimes(CreateCliTokenCommand, 1);
      });
    });

    describe('execute', () => {
      it('should make a cli API call with the supplied command payload', async () => {
        const stdOut = 'output';
        const stdError = 'error';

        nock('https://mwaa.com')
          .post('/aws_mwaa/cli')
          .reply(200, {
            stderr: Buffer.from(stdError).toString('base64'),
            stdout: Buffer.from(stdOut).toString('base64'),
          });

        const cli = new DagsCli('my-env');
        const result = await cli.execute('dags trigger', { key: 'value' });

        expect(result).toEqual({ stdOut, stdError });
      });

      it('should work without configuration', async () => {
        const stdOut = 'output';
        const stdError = 'error';

        nock('https://mwaa.com')
          .post('/aws_mwaa/cli', 'dags trigger')
          .reply(200, {
            stderr: Buffer.from(stdError).toString('base64'),
            stdout: Buffer.from(stdOut).toString('base64'),
          });

        const cli = new DagsCli('my-env');
        const result = await cli.execute('dags trigger');

        expect(result).toEqual({ stdOut, stdError });
      });

      it('should throw an error if std out is missing', async () => {
        nock('https://mwaa.com').post('/aws_mwaa/cli', 'dags trigger').reply(200, {});

        const cli = new DagsCli('my-env');

        try {
          await cli.execute('dags trigger');
        } catch (error) {
          expect(error.message.includes('The dags trigger failed to execute')).toBeTruthy();
        }
      });
    });

    describe('unpauseDag', () => {
      afterEach(() => {
        jest.resetAllMocks();
      });

      it('should execute the dags unpause cli command', async () => {
        const cli = new DagsCli('my-env');
        const expectedResult = {
          stdOut: 'Command output <paused: False> more output',
          stdError: '',
        };

        jest.spyOn(cli, 'execute').mockResolvedValue(expectedResult);

        const result = await cli.unpauseDag('my-dag');
        expect(result).toEqual(expectedResult);
      });

      it('should throw an error if the supplied dag was not unpaused', async () => {
        const cli = new DagsCli('my-env');
        const expectedResult = {
          stdOut: 'Command output <paused: True> more output',
          stdError: '',
        };

        jest.spyOn(cli, 'execute').mockResolvedValue(expectedResult);

        expect.assertions(1);
        try {
          await cli.unpauseDag('my-dag');
        } catch (error) {
          expect(error.message.includes('Dag [my-dag] unpause failed')).toBeTruthy();
        }
      });
    });

    describe('triggerDag', () => {
      afterEach(() => {
        jest.resetAllMocks();
      });

      it('should execute the dags trigger cli command', async () => {
        const cli = new DagsCli('my-env');
        const expectedResult = {
          stdOut: 'Command output <triggered: True> more output',
          stdError: 'some text',
        };

        jest.spyOn(cli, 'execute').mockResolvedValue(expectedResult);

        const result = await cli.triggerDag('my-dag');
        expect(result).toEqual(expectedResult);
      });

      it('should throw an error if the supplied dag was not triggered', async () => {
        const cli = new DagsCli('my-env');
        const expectedResult = {
          stdOut: 'Command output <triggered: False> more output',
          stdError: 'some text',
        };

        jest.spyOn(cli, 'execute').mockResolvedValue(expectedResult);

        expect.assertions(1);
        try {
          await cli.triggerDag('my-dag');
        } catch (error) {
          expect(error.message.includes('Dag [my-dag] trigger failed')).toBeTruthy();
        }
      });
    });
  });
});
