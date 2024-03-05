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

import * as dotenv from 'dotenv';
dotenv.config();

import { MwaaMainStackProps } from '../infrastructure/mwaa-main-stack';

export const MWAA_DEFAULT_DAGS_S3_PATH = 'dags';
export const MWAA_DEFAULT_RESOURCES_FOLDER = 'mwaairflow';
export const MWAA_DEFAULT_ENV_BACKUP_FILE = 'environment-backup.json';
export const MWAA_DEFAULT_METADATA_EXPORT_DAG_NAME = 'mwaa_export_data';
export const MWAA_DEFAULT_METADATA_IMPORT_DAG_NAME = 'mwaa_import_data';
export const MWAA_DEFAULT_MODIFY_EXECUTION_ROLE = 'no';

export const SFN_DEFAULT_POLL_TIMEOUT_MINS = 60;
export const SFN_DEFAULT_PAUSE_TIMEOUT_MINS = 60;
export const SFN_DEFAULT_RESUME_TIMEOUT_MINS = 60;
export const SFN_DEFAULT_POLL_FREQUENCY_SECS = 60;

export const MWAA_DEFAULT_NOTIFICATION_TYPES = ['FAILED', 'TIMED_OUT', 'ABORTED'];

export type Config = MwaaMainStackProps;

function configuration(): Config {
  return {
    region: envOrError('CDK_DEFAULT_REGION'),
    account: envOrError('CDK_DEFAULT_ACCOUNT'),
    mainStackName: envOrError('MWAA_MAIN_STACK_NAME'),
    environmentName: envOrError('MWAA_ENV_NAME'),
    sourceBucketName: envOrError('MWAA_SOURCE_BUCKET_NAME'),
    executionRoleArn: envOrError('MWAA_EXECUTION_ROLE_ARN'),
    updateExecutionRole: envOrError('MWAA_UPDATE_EXECUTION_ROLE'),
    pauseCronSchedule: envOrError('MWAA_PAUSE_CRON_SCHEDULE'),
    resumeCronSchedule: envOrError('MWAA_RESUME_CRON_SCHEDULE'),
    scheduleTimeZone: envOrError('MWAA_SCHEDULE_TIME_ZONE'),
    environmentVersion: envOrError('MWAA_ENV_VERSION'),

    vpcId: envOrDefault('MWAA_VPC_ID', ''),
    subnetIds: envOrDefault('MWAA_VPC_SUBNETS', []),
    securityGroups: envOrDefault('MWAA_VPC_SECURITY_GROUPS', []),

    dagsS3Path: envOrDefault('MWAA_DAGS_S3_PATH', MWAA_DEFAULT_DAGS_S3_PATH),

    notificationTypes: envOrDefault('MWAA_NOTIFICATION_TYPES', MWAA_DEFAULT_NOTIFICATION_TYPES),
    emails: envOrDefault('MWAA_NOTIFICATION_EMAILS', []),

    mwaaResources: envOrDefault('MWAA_RESOURCES_FOLDER', MWAA_DEFAULT_RESOURCES_FOLDER),
    environmentBackupFile: envOrDefault('MWAA_ENV_BACKUP_FILE', MWAA_DEFAULT_ENV_BACKUP_FILE),
    metadataExportDagName: envOrDefault('MWAA_METADATA_EXPORT_DAG_NAME', MWAA_DEFAULT_METADATA_EXPORT_DAG_NAME),
    metadataImportDagName: envOrDefault('MWAA_METADATA_IMPORT_DAG_NAME', MWAA_DEFAULT_METADATA_IMPORT_DAG_NAME),

    pollTimeoutMins: envOrDefault('SFN_POLL_TIMEOUT_MINS', SFN_DEFAULT_POLL_TIMEOUT_MINS),
    pauseTimeoutMins: envOrDefault('SFN_PAUSE_TIMEOUT_MINS', SFN_DEFAULT_PAUSE_TIMEOUT_MINS),
    resumeTimoutMins: envOrDefault('SFN_RESUME_TIMEOUT_MINS', SFN_DEFAULT_RESUME_TIMEOUT_MINS),
    pollFrequencySeconds: envOrDefault('SFN_POLL_FREQUENCY_SECS', SFN_DEFAULT_POLL_FREQUENCY_SECS),
  };
}

function envOrError<T>(field: string): T {
  if (!process.env[field]) {
    throw new Error(`The required environment variable [${field}] is missing!`);
  }

  const value = process.env[field]!.trim();
  if (!value) {
    throw new Error(`The required environment variable [${field}] is empty!`);
  }

  return convertToType(field, value) as T;
}

function envOrDefault<T>(field: string, defaultValue: T): T {
  const value: string | T | undefined = process.env[field] ? process.env[field]!.trim() : process.env[field];

  if (value) {
    return convertToType(field, value) as T;
  }
  return defaultValue;
}

function convertToType<T>(field: string, originalValue: string): T {
  if (originalValue.startsWith('[')) {
    const result = toArray(originalValue);
    if (result.length === 0) {
      throw new Error(`Illegal value supplied for the environment variable [${field}]`);
    }
    return result as T;
  }
  if(field=='CDK_DEFAULT_ACCOUNT') {
    return originalValue as T;
  }

  const numValue = toNumber(originalValue);
  return (isNumber(numValue) ? numValue : originalValue) as T;
}

function toArray<T>(value: string): T[] {
  const records: T[] = [];
  value
    .replace('[', '')
    .replace(']', '')
    .split(',')
    .forEach((val) => {
      const record = val.trim();
      if (record) {
        const num = toNumber(record);
        records.push((isNumber(num) ? num : record) as T);
      }
    });
  return records;
}

function toNumber(value: string): number {
  return Number(value);
}

function isNumber(num: number): boolean {
  return !Number.isNaN(num);
}

export default configuration;
