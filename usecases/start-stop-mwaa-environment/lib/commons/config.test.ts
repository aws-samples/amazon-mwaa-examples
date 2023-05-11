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

import configuration from '../../lib/commons/config';
import { prepareTestEnvironment } from './prepare-test-environment';

describe('config', () => {
  it('should require the required environment variables', () => {
    const requiredVars = [
      'CDK_DEFAULT_REGION',
      'CDK_DEFAULT_ACCOUNT',
      'MWAA_MAIN_STACK_NAME',
      'MWAA_ENV_NAME',
      'MWAA_ENV_VERSION',
      'MWAA_SOURCE_BUCKET_NAME',
      'MWAA_EXECUTION_ROLE_ARN',
      'MWAA_UPDATE_EXECUTION_ROLE',
      'MWAA_PAUSE_CRON_SCHEDULE',
      'MWAA_RESUME_CRON_SCHEDULE',
      'MWAA_SCHEDULE_TIME_ZONE',
    ];
    expect.assertions(requiredVars.length);

    requiredVars.forEach((name) => {
      prepareTestEnvironment();
      process.env[name] = '';
      try {
        configuration();
      } catch (error) {
        expect(error.message).toEqual(`The required environment variable [${name}] is missing!`);
      }
    });
  });

  it('should require the non-empty environment variables', () => {
    const requiredVars = [
      'CDK_DEFAULT_REGION',
      'CDK_DEFAULT_ACCOUNT',
      'MWAA_MAIN_STACK_NAME',
      'MWAA_ENV_NAME',
      'MWAA_ENV_VERSION',
      'MWAA_SOURCE_BUCKET_NAME',
      'MWAA_EXECUTION_ROLE_ARN',
      'MWAA_UPDATE_EXECUTION_ROLE',
      'MWAA_PAUSE_CRON_SCHEDULE',
      'MWAA_RESUME_CRON_SCHEDULE',
      'MWAA_SCHEDULE_TIME_ZONE',
    ];
    expect.assertions(requiredVars.length);

    requiredVars.forEach((name) => {
      prepareTestEnvironment();
      process.env[name] = ' ';
      try {
        configuration();
      } catch (error) {
        expect(error.message).toEqual(`The required environment variable [${name}] is empty!`);
      }
    });
  });

  it('should use defaults for missing optional environment variables', () => {
    const optionalVars = [
      'MWAA_DAGS_S3_PATH',
      'MWAA_NOTIFICATION_EMAILS',
      'MWAA_NOTIFICATION_TYPES',
      'MWAA_RESOURCES_FOLDER',
      'MWAA_ENV_BACKUP_FILE',
      'MWAA_METADATA_EXPORT_DAG_NAME',
      'MWAA_METADATA_IMPORT_DAG_NAME',
      'SFN_POLL_TIMEOUT_MINS',
      'SFN_PAUSE_TIMEOUT_MINS',
      'SFN_RESUME_TIMEOUT_MINS',
    ];
    expect.assertions(optionalVars.length + 1);

    prepareTestEnvironment();
    optionalVars.forEach((name) => {
      process.env[name] = '';
    });
    process.env['SFN_POLL_FREQUENCY_SECS'] = '40';

    const config = configuration();
    expect(config.dagsS3Path).toEqual('dags');
    expect(config.emails).toEqual([]);
    expect(config.notificationTypes).toEqual(['FAILED', 'TIMED_OUT', 'ABORTED']);
    expect(config.mwaaResources).toEqual('mwaairflow');
    expect(config.environmentBackupFile).toEqual('environment-backup.json');
    expect(config.metadataExportDagName).toEqual('mwaa_export_data');
    expect(config.metadataImportDagName).toEqual('mwaa_import_data');
    expect(config.pollTimeoutMins).toEqual(60);
    expect(config.pauseTimeoutMins).toEqual(60);
    expect(config.resumeTimoutMins).toEqual(60);
    expect(config.pollFrequencySeconds).toEqual(40);
  });

  it('should be able to auto-convert string to numbers for an array input', () => {
    const optionalVars = ['MWAA_NOTIFICATION_TYPES'];

    prepareTestEnvironment();
    optionalVars.forEach((name) => {
      process.env[name] = '';
    });
    process.env['MWAA_NOTIFICATION_TYPES'] = '[40]';

    const config = configuration();
    expect(config.notificationTypes).toEqual([40]);
  });

  it('should error out if illegal array is provided', () => {
    prepareTestEnvironment();
    process.env.MWAA_NOTIFICATION_EMAILS = '[,]';

    expect.assertions(1);
    try {
      configuration();
    } catch (error) {
      expect(error.message).toEqual('Illegal value supplied for the environment variable [MWAA_NOTIFICATION_EMAILS]');
    }
  });
});
