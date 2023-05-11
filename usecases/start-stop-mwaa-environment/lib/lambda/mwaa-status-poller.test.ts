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

import { mockClient } from 'aws-sdk-client-mock';
import * as mwaa from '@aws-sdk/client-mwaa';
import { COMPLETE, INCOMPLETE, MwaaStatusPoller } from '../../lib/lambda/mwaa-status-poller';

describe('MwaaStatusPoller', () => {
  describe('Constructor', () => {
    it('should supply a default mwaa sdk client if not passed as an argument', () => {
      const mwaaPoller = new MwaaStatusPoller('test');
      expect(mwaaPoller['client']).toBeTruthy();
    });
  });

  describe('checkCreated', () => {
    it('should return a complete status when environment is available', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.resolves({
        Environment: {
          Status: 'AVAILABLE',
        },
      });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkCreated();

      expect(result).toEqual(COMPLETE);
    });

    it('should return an incomplete status when environment is unavailable', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.resolves({
        Environment: {
          Status: 'CREATING',
        },
      });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkCreated();

      expect(result).toEqual(INCOMPLETE);
    });

    it('should return an incomplete status when environment is undefined', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.resolves({});

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkCreated();

      expect(result).toEqual(INCOMPLETE);
    });

    it('should return an incomplete status when environment throws a resource not found error', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.rejects({ name: 'ResourceNotFoundException' });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkCreated();

      expect(result).toEqual(INCOMPLETE);
    });

    it('should throw other errors returned by the environment', async () => {
      expect.assertions(1);

      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.rejects({ name: 'ExpiredTokenException' });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      try {
        await statusPoller.checkCreated();
      } catch (error) {
        expect(error.name).toEqual('ExpiredTokenException');
      }
    });
  });

  describe('checkDeleted', () => {
    it('should return a complete status when the environment is deleted', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.resolves({
        Environment: {
          Status: 'DELETED',
        },
      });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkDeleted();

      expect(result).toEqual(COMPLETE);
    });

    it('should return an incomplete status when environment is not completely deleted', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.resolves({
        Environment: {
          Status: 'AVAILABLE',
        },
      });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkDeleted();

      expect(result).toEqual(INCOMPLETE);
    });

    it('should return an incomplete status when environment is undefined', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.resolves({});

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkDeleted();

      expect(result).toEqual(INCOMPLETE);
    });

    it('should return a complete status when environment throws a resource not found error', async () => {
      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.rejects({ name: 'ResourceNotFoundException' });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      const result = await statusPoller.checkDeleted();

      expect(result).toEqual(COMPLETE);
    });

    it('should throw other errors returned by the environment', async () => {
      expect.assertions(1);

      const mwaaClient = new mwaa.MWAAClient({});
      const mwaaClientMock = mockClient(mwaaClient);
      mwaaClientMock.rejects({ name: 'ExpiredTokenException' });

      const statusPoller = new MwaaStatusPoller('my-env', mwaaClient);
      try {
        await statusPoller.checkDeleted();
      } catch (error) {
        expect(error.name).toEqual('ExpiredTokenException');
      }
    });
  });
});
