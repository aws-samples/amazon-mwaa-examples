#!/usr/bin/env python3
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
"""

"""
AWS Lambda function to generate CloudWatch metrics and dashboard for MWAA Serverless workflows
"""

import boto3
from botocore.loaders import Loader
import json
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def setup_mwaa_serverless_client(region):
    return boto3.client('mwaa-serverless', region_name=region)

def get_last_processed_time():
    """Get last processed timestamp from DynamoDB or return default"""
    try:
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('STATE_TABLE', 'mwaa-metrics-state')
        table = dynamodb.Table(table_name)
        
        response = table.get_item(Key={'id': 'last_processed'})
        if 'Item' in response:
            return datetime.fromisoformat(response['Item']['timestamp'])
    except Exception as e:
        print(f"Error getting last processed time: {e}")
    
    # Default to 30 days ago
    return datetime.now(timezone.utc) - timedelta(days=30)

def update_last_processed_time(timestamp):
    """Update last processed timestamp in DynamoDB"""
    try:
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('STATE_TABLE', 'mwaa-metrics-state')
        
        # Create table if it doesn't exist
        try:
            table = dynamodb.Table(table_name)
            table.load()  # This will raise an exception if table doesn't exist
        except:
            print(f"Creating DynamoDB table: {table_name}")
            table = dynamodb.create_table(
                TableName=table_name,
                KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'id', 'AttributeType': 'S'}],
                BillingMode='PAY_PER_REQUEST'
            )
            table.wait_until_exists()
        
        table.put_item(Item={
            'id': 'last_processed',
            'timestamp': timestamp.isoformat()
        })
    except Exception as e:
        print(f"Error updating last processed time: {e}")

def send_zero_metrics_for_inactive_workflows(cloudwatch, namespace, current_time):
    """Send zero metrics for workflows with no recent activity to maintain continuous lines"""
    try:
        # Get all workflows
        region = os.environ.get('AWS_REGION', 'us-east-2')
        mwaas = setup_mwaa_serverless_client(region)
        workflows_response = mwaas.list_workflows()
        
        for workflow in workflows_response['Workflows']:
            workflow_id = workflow['WorkflowArn'].split('/')[-1]
            
            # Send zero metrics to ensure continuous lines
            metrics_data = [
                {
                    'MetricName': 'TotalRuns',
                    'Dimensions': [{'Name': 'WorkflowId', 'Value': workflow_id}],
                    'Value': 0,
                    'Unit': 'Count',
                    'Timestamp': current_time
                },
                {
                    'MetricName': 'SuccessfulRuns',
                    'Dimensions': [{'Name': 'WorkflowId', 'Value': workflow_id}],
                    'Value': 0,
                    'Unit': 'Count',
                    'Timestamp': current_time
                },
                {
                    'MetricName': 'FailedRuns',
                    'Dimensions': [{'Name': 'WorkflowId', 'Value': workflow_id}],
                    'Value': 0,
                    'Unit': 'Count',
                    'Timestamp': current_time
                },
                {
                    'MetricName': 'TaskSuccess',
                    'Dimensions': [{'Name': 'WorkflowId', 'Value': workflow_id}],
                    'Value': 0,
                    'Unit': 'Count',
                    'Timestamp': current_time
                },
                {
                    'MetricName': 'TaskFailure',
                    'Dimensions': [{'Name': 'WorkflowId', 'Value': workflow_id}],
                    'Value': 0,
                    'Unit': 'Count',
                    'Timestamp': current_time
                }
            ]
            
            cloudwatch.put_metric_data(
                Namespace=namespace,
                MetricData=metrics_data
            )
            
    except Exception as e:
        print(f"Error sending zero metrics: {e}")

def collect_workflow_metrics(mwaas, cloudwatch, last_processed_time):
    """Collect metrics from MWAA workflows and send to CloudWatch"""
    current_time = datetime.now(timezone.utc)
    namespace = 'MWAA/Serverless'
    
    # Get all workflows
    workflows_response = mwaas.list_workflows()
    workflows = workflows_response['Workflows']
    
    print(f"Processing {len(workflows)} workflows")
    
    for workflow in workflows:
        workflow_arn = workflow['WorkflowArn']
        workflow_id = workflow_arn.split('/')[-1]
        
        # Workflow-level metrics
        workflow_status = workflow['WorkflowStatus']
        trigger_mode = workflow['TriggerMode']
        
        # Send workflow status metric
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': 'WorkflowStatus',
                    'Dimensions': [
                        {'Name': 'WorkflowId', 'Value': workflow_id}
                    ],
                    'Value': 1 if workflow_status == 'READY' else 0,
                    'Unit': 'Count',
                    'Timestamp': current_time
                }
            ]
        )
        
        # Send trigger mode metric
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': 'WorkflowEnabled',
                    'Dimensions': [
                        {'Name': 'WorkflowId', 'Value': workflow_id}
                    ],
                    'Value': 1 if trigger_mode != 'disabled' else 0,
                    'Unit': 'Count',
                    'Timestamp': current_time
                }
            ]
        )
        
        # Get workflow runs
        try:
            runs_response = mwaas.list_workflow_runs(WorkflowArn=workflow_arn)
            runs = runs_response['WorkflowRuns']
            
            # Process only new runs since last processed time
            new_runs = []
            for run in runs:
                try:
                    run_id = run['RunId']
                    run_details = mwaas.get_workflow_run(RunId=run_id, WorkflowArn=workflow_arn)
                    
                    started_time = run_details['RunDetail']['StartedOn']
                    if started_time > last_processed_time:
                        new_runs.append((run_id, run_details))
                except Exception as e:
                    print(f"Error processing workflow run {run_id}: {e}")     

            print(f"Found {len(new_runs)} new runs for workflow {workflow_id}")
            
            # Process new runs
            for run_id, run_details in new_runs:
                process_workflow_run_metrics(mwaas, cloudwatch, workflow_arn, workflow_id, run_id, run_details, namespace)
                
        except Exception as e:
            print(f"Error processing workflow {workflow_id}: {e}")

def process_workflow_run_metrics(mwaas, cloudwatch, workflow_arn, workflow_id, run_id, run_details, namespace):
    """Process metrics for a single workflow run"""
    run_state = run_details['RunDetail']['RunState']
    started_time = run_details['RunDetail']['StartedOn']
    ended_time = run_details['RunDetail'].get('CompletedOn')
    
    # Calculate duration if run is complete
    duration = None
    if ended_time:
        duration = (ended_time - started_time).total_seconds()
    
    # Send total runs metric
    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                'MetricName': 'TotalRuns',
                'Dimensions': [
                    {'Name': 'WorkflowId', 'Value': workflow_id}
                ],
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': started_time
            }
        ]
    )
    
    # Send success/failure metrics
    metric_name=f"Run{run_state.lower().capitalize()}"
    print(f"Writing {metric_name} for workflow {workflow_id}")
    
    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                'MetricName': metric_name,
                'Dimensions': [
                    {'Name': 'WorkflowId', 'Value': workflow_id}
                ],
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': started_time
            }
        ]
    )
    
    # Send duration metric if available
    if duration:
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': 'RunDuration',
                    'Dimensions': [
                        {'Name': 'WorkflowId', 'Value': workflow_id}
                    ],
                    'Value': duration,
                    'Unit': 'Seconds',
                    'Timestamp': started_time
                }
            ]
        )
    
    # Process task instances
    task_instances = run_details['RunDetail']['TaskInstances']
    for task_instance_id in task_instances:
        if not task_instance_id.endswith("_0"):  # Skip certain task instances
            try:
                task_details = mwaas.get_task_instance(
                    RunId=run_id,
                    WorkflowArn=workflow_arn,
                    TaskInstanceId=task_instance_id
                )
                
                process_task_metrics(cloudwatch, workflow_id, task_details, namespace)
                
            except Exception as e:
                print(f"Error processing task {task_instance_id}: {e}")

def process_task_metrics(cloudwatch, workflow_id, task_details, namespace):
    """Process metrics for a single task instance"""
    task_id = task_details['TaskId']
    status = task_details['Status']
    started_time = task_details.get('StartedAt')
    ended_time = task_details.get('EndedAt')
    
    if not started_time:
        return
    
    # Task success metric
    metric_name=f"Task{status.lower().capitalize()}"
    print(f"Writing {metric_name} for task {task_id} in workflow {workflow_id}")
    
    cloudwatch.put_metric_data(
        Namespace=namespace,
        MetricData=[
            {
                'MetricName': metric_name,
                'Dimensions': [
                    {'Name': 'WorkflowId', 'Value': workflow_id},
                    {'Name': 'TaskInstanceName', 'Value': task_id}
                ],
                'Value': 1,
                'Unit': 'Count',
                'Timestamp': started_time
            }
        ]
    )

    # Task duration if available
    if ended_time and started_time:
        duration = (ended_time - started_time).total_seconds()
        cloudwatch.put_metric_data(
            Namespace=namespace,
            MetricData=[
                {
                    'MetricName': 'TaskDuration',
                    'Dimensions': [
                        {'Name': 'WorkflowId', 'Value': workflow_id},
                        {'Name': 'TaskInstanceName', 'Value': task_id}
                    ],
                    'Value': duration,
                    'Unit': 'Seconds',
                    'Timestamp': ended_time
                }
            ]
        )

def lambda_handler(event, context):
    """Main Lambda handler"""
    try:
        region = os.environ.get('AWS_REGION', 'us-east-2')
        
        # Setup clients
        mwaas = setup_mwaa_serverless_client(region)
        cloudwatch = boto3.client('cloudwatch', region_name=region)
        
        # Get last processed time to only process new data
        last_processed_time = get_last_processed_time()
        print(f"Processing data since: {last_processed_time}")
        
        # Collect and send metrics
        collect_workflow_metrics(mwaas, cloudwatch, last_processed_time)
        
        # Send zero metrics to maintain continuous lines
        current_time = datetime.now(timezone.utc)
        send_zero_metrics_for_inactive_workflows(cloudwatch, 'MWAA/Serverless', current_time)
        
        # Update last processed time
        update_last_processed_time(current_time)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'MWAA metrics processed successfully',
                'processed_time': current_time.isoformat()
            })
        }
        
    except Exception as e:
        print(f"Error in lambda_handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

# Local testing support
if __name__ == '__main__':
    """Local testing mode"""
    import sys
    
    # Mock Lambda context for local testing
    class MockContext:
        def __init__(self):
            self.function_name = 'mwaa-metrics-lambda'
            self.invoked_function_arn = 'arn:aws:lambda:us-east-2:123456789012:function:mwaa-metrics-lambda'
            self.aws_request_id = 'test-request-id'
    
    # Set environment variables for local testing
    os.environ.setdefault('AWS_REGION', 'us-east-2')
    os.environ.setdefault('STATE_TABLE', 'mwaa-metrics-state')
    
    # Run the lambda handler
    test_event = {}
    result = lambda_handler(test_event, MockContext())
    
    print("Lambda execution result:")
    print(json.dumps(result, indent=2))
