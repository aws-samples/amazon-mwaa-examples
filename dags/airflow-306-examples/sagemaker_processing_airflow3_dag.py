"""
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

Required IAM Permissions:
- sagemaker:CreateProcessingJob - Create SageMaker processing jobs
- sagemaker:DescribeProcessingJob - Get processing job status
- s3:GetObject - Read input data from S3
- s3:PutObject - Write output data to S3
- s3:CreateBucket - Create S3 buckets for outputs
- s3:ListBucket - List S3 bucket contents
- iam:PassRole - Pass execution role to SageMaker
- ecr:GetAuthorizationToken - Access ECR for container images
- ecr:BatchCheckLayerAvailability - Check ECR layer availability
- ecr:GetDownloadUrlForLayer - Download ECR layers
- ecr:BatchGetImage - Get ECR images
"""

from datetime import datetime
from airflow.decorators import dag
from airflow.providers.amazon.aws.operators.s3 import (
    S3CreateBucketOperator,
    S3DeleteBucketOperator,
    S3CreateObjectOperator
)
from airflow.providers.amazon.aws.operators.sagemaker import SageMakerProcessingOperator
from airflow.providers.amazon.aws.sensors.sagemaker import SageMakerProcessingSensor
from airflow.models.param import Param

@dag(
    dag_id='sagemaker_processing_dag',
    start_date=datetime(2024, 1, 1),
    schedule=None,
    params={
        'role_arn': Param(
            default='arn:aws:iam::111122223333:role/service-role/MyExecutionRole',
            type='string',
            description='IAM role ARN'
        ),
        'region': Param(
            default='us-east-2',
            type='string',
            description='AWS Region'
        )
    },
    description='Self-contained SageMaker Processing job example with resource cleanup'
)
def sagemaker_processing_dag():
    
    # Creates S3 bucket for storing processing job data and outputs
    create_bucket = S3CreateBucketOperator(
        task_id='create_processing_bucket',
        bucket_name='sagemaker-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}',
        region_name='{{ params.region }}'
    )
    
    # Uploads Python processing script to S3 for SageMaker to execute
    upload_script = S3CreateObjectOperator(
        task_id='upload_processing_script',
        s3_bucket='sagemaker-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}',
        s3_key='code/preprocessing.py',
        data='''#!/usr/bin/env python3
import os
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-data', type=str, default='/opt/ml/processing/input')
    parser.add_argument('--output-data', type=str, default='/opt/ml/processing/output')
    args = parser.parse_args()
    
    print("Starting data processing...")
    
    # Create sample data if input directory is empty
    input_files = os.listdir(args.input_data) if os.path.exists(args.input_data) else []
    
    if not input_files:
        print("No input files found, creating sample data...")
        # Generate sample dataset
        np.random.seed(42)
        data = {
            'feature1': np.random.normal(0, 1, 1000),
            'feature2': np.random.normal(5, 2, 1000),
            'feature3': np.random.exponential(1, 1000),
            'target': np.random.choice([0, 1], 1000)
        }
        df = pd.DataFrame(data)
    else:
        # Process existing input files
        print(f"Processing input files: {input_files}")
        df_list = []
        for file in input_files:
            if file.endswith('.csv'):
                file_path = os.path.join(args.input_data, file)
                df_list.append(pd.read_csv(file_path))
        df = pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()
    
    if not df.empty:
        # Apply preprocessing
        print("Applying preprocessing transformations...")
        
        # Separate features and target
        feature_cols = [col for col in df.columns if col != 'target']
        if feature_cols:
            # Standardize features
            scaler = StandardScaler()
            df[feature_cols] = scaler.fit_transform(df[feature_cols])
        
        # Save processed data
        os.makedirs(args.output_data, exist_ok=True)
        output_path = os.path.join(args.output_data, 'processed_data.csv')
        df.to_csv(output_path, index=False)
        
        # Save processing statistics
        stats = {
            'total_rows': len(df),
            'total_features': len(feature_cols),
            'processing_timestamp': pd.Timestamp.now().isoformat()
        }
        stats_df = pd.DataFrame([stats])
        stats_path = os.path.join(args.output_data, 'processing_stats.csv')
        stats_df.to_csv(stats_path, index=False)
        
        print(f"Processing complete. Processed {len(df)} rows with {len(feature_cols)} features.")
        print(f"Output saved to: {output_path}")
    else:
        print("No data to process.")

if __name__ == "__main__":
    main()
''',
        aws_conn_id='aws_default'
    )
    
    # Uploads sample CSV data to S3 as input for the processing job
    upload_input_data = S3CreateObjectOperator(
        task_id='upload_input_data',
        s3_bucket='sagemaker-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}',
        s3_key='input/sample_data.csv',
        data='''feature1,feature2,feature3,target
1.5,2.3,0.8,1
-0.5,1.2,1.5,0
2.1,3.4,0.3,1
-1.2,0.8,2.1,0
0.8,2.8,1.2,1
''',
        aws_conn_id='aws_default'
    )
    
    # Executes SageMaker processing job with scikit-learn container for data preprocessing
    # Following AWS documentation pattern for scikit-learn processing container
    processing_job = SageMakerProcessingOperator(
        task_id='run_processing_job',
        config={
            'ProcessingJobName': 'airflow-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}',
            'ProcessingResources': {
                'ClusterConfig': {
                    'InstanceCount': 1,
                    'InstanceType': 'ml.m5.large',
                    'VolumeSizeInGB': 30
                }
            },
            'AppSpecification': {
                # Using XGBoost container as it's verified to work in this environment
                'ImageUri': '683313688378.dkr.ecr.us-east-2.amazonaws.com/sagemaker-scikit-learn:0.23-1-cpu-py3',
                'ContainerEntrypoint': ['python3', '/opt/ml/processing/input/code/preprocessing.py']
            },
            'ProcessingInputs': [
                {
                    'InputName': 'code',
                    'S3Input': {
                        'S3Uri': 's3://sagemaker-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}/code/',
                        'LocalPath': '/opt/ml/processing/input/code',
                        'S3DataType': 'S3Prefix',
                        'S3InputMode': 'File'
                    }
                },
                {
                    'InputName': 'input-data',
                    'S3Input': {
                        'S3Uri': 's3://sagemaker-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}/input/',
                        'LocalPath': '/opt/ml/processing/input/data',
                        'S3DataType': 'S3Prefix',
                        'S3InputMode': 'File'
                    }
                }
            ],
            'ProcessingOutputConfig': {
                'Outputs': [
                    {
                        'OutputName': 'processed-data',
                        'S3Output': {
                            'S3Uri': 's3://sagemaker-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}/output/',
                            'LocalPath': '/opt/ml/processing/output',
                            'S3UploadMode': 'EndOfJob'
                        }
                    }
                ]
            },
            'RoleArn': '{{ params.role_arn }}'
        }
    )
    
    # Waits for SageMaker processing job to complete successfully
    processing_sensor = SageMakerProcessingSensor(
        task_id='wait_for_processing_completion',
        job_name='airflow-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}',
        timeout=1800,  # 30 minutes
        poke_interval=60  # Check every minute
    )
    
    # Deletes S3 bucket and all contents for cleanup (runs regardless of job success/failure)
    cleanup_bucket = S3DeleteBucketOperator(
        task_id='cleanup_processing_bucket',
        bucket_name='sagemaker-processing-{{ ds_nodash }}-{{ ts_nodash | lower }}',
        force_delete=True,
        trigger_rule='all_done'  # Run regardless of upstream task success/failure
    )
    
    # Define task dependencies
    create_bucket >> [upload_script, upload_input_data] >> processing_job >> processing_sensor >> cleanup_bucket

# Create DAG instance
dag_instance = sagemaker_processing_dag()
