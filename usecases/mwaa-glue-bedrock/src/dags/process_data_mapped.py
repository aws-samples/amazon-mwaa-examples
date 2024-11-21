import json
from airflow import DAG
from airflow.providers.amazon.aws.operators.bedrock import BedrockInvokeModelOperator
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator, S3DeleteObjectsOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.decorators import task
from datetime import datetime, timedelta
import mwaa_config
import random, string
import boto3

# Default arguments for the DAG
default_args = {
  'owner': 'airflow',
  'depends_on_past': False,
  'email_on_failure': False,
  'email_on_retry': False,
  'retries': 1,
  'retry_delay': timedelta(minutes=5),
}

STACK_NAME = mwaa_config.STACK_NAME

# Configure S3 bucket for outputs.
S3_BUCKET_NAME = mwaa_config.BUCKET_NAME
S3_PREFIX = "export"
S3_BEDROCK_PREFIX = "output"

# Glue Connector details and job settings
GLUE_SFDC_CONNECTION_NAME = mwaa_config.SALESFORCE_CONNECTION
MAX_GLUE_JOB_CONCURRENCY = 5

# Glue job name
GLUE_JOB_NAME = "eb-mwaa-glue-bedrock_fetch_salesforce_cases"

# Glue execution role
GLUE_IAM_ROLE = mwaa_config.GLUE_EXECUTION_ROLE

# Task to trigger the Glue job
glue_job = GlueJobOperator(
  task_id="trigger_glue_job",
  job_name=GLUE_JOB_NAME,
  create_job_kwargs={"GlueVersion": "4.0", "NumberOfWorkers": 2, "WorkerType": "G.1X"},
)

# List objects in the export folder and get their keys
@task
def list_s3_objects():
  s3 = boto3.client('s3')
  response = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix=S3_PREFIX)
  return [obj['Key'] for obj in response.get('Contents', [])]

# Read JSONL file from S3 and parse each line as a JSON object
@task
def read_jsonl_from_s3(s3_keys):
    s3 = boto3.client('s3')
    all_json_objects = []

    for s3_key in s3_keys:
        response = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
        content = response['Body'].read().decode('utf-8')
        json_objects = [json.loads(line) for line in content.splitlines()]
        all_json_objects.extend(json_objects)
    
    return all_json_objects

# Extract Salesforce event data from the JSON
@task
def extract_case_data(execution_id, case_data):
    # Extract relevant case data from S3 Content
    return {
        "ExecutionId": execution_id,
        "ParentId": case_data.get('Id'),
        "Subject": case_data.get('Subject'),
        "Description": case_data.get('Description'),
        "CaseNumber": case_data.get('CaseNumber'),
        "Status": case_data.get('Status'),
        "Priority": case_data.get('Priority')
    }

@task
def generate_execution_id():
    # Extract relevant data from EventBridge event
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

# Prepare Bedrock input from extracted case data
@task
def prepare_bedrock_input(case_data):
  print(f"Case data: {case_data}")

  prompt_template = """
  A new case has been created in Salesforce with the following details:
  Case Number: {case_number}
  Subject: {subject}
  Status: {status}
  Priority: {priority}
  Description: {description}

  Read the problem and suggest a solution.
  Do not write any introductory comments, write directly the resolution and steps needed to solve the problem.
  """
  prompt = prompt_template.format(
      case_number=case_data['CaseNumber'],
      subject=case_data['Subject'],
      status=case_data['Status'],
      priority=case_data['Priority'],
      description=case_data['Description']
  )
  return {
      "max_tokens": 4096,
      "anthropic_version": "bedrock-2023-05-31",
      "messages": [
        {"role": "user", "content": prompt}
      ],
  }

@task
def process_bedrock_output(zipped_data):
    bedrock_response, case_data = zipped_data
    comment = bedrock_response['content'][0]['text']
    comment = f"Amazon Bedrock: {comment}"
    json_string = {
        "ParentId": case_data['ParentId'],
        "CommentBody": comment,
        "IsPublished": False,
        "IsDeleted": False
    }
    return json.dumps(json_string)

@task
def generate_s3_key(zipped_data):
  print(f"Zipped Data {zipped_data}")

  s3_body, case_data = zipped_data
  print(f"Case Data {case_data}")
  print(f"S3 Body {s3_body}")

  execution_id = case_data.get("ExecutionId")
  parent_id = case_data.get("ParentId")
  print(f"Execution ID: {execution_id}, Parent ID: {parent_id}")

  return {
      "s3_key": f"{S3_BEDROCK_PREFIX}/{execution_id}/{parent_id}.json",
      "data": s3_body
  }

with DAG(
  'process-salesforce-data-mapped',
  default_args=default_args,
  description='Process Salesforce data with Glue and Bedrock using Mapped tasks',
  schedule_interval=None,  # Manually triggered DAG
  start_date=datetime(2024, 10, 9),
  catchup=False,
) as dag:

  # Generate execution id
  execution_id = generate_execution_id()

  # Trigger Glue job to fetch Salesforce cases
  trigger_glue_job = glue_job

  # List objects in the S3 export folder after Glue job completes
  s3_keys = list_s3_objects()

  # Read and parse JSONL data from each S3 object, returning a flattened list of JSON objects
  jsonl_data = read_jsonl_from_s3(s3_keys=s3_keys)

  
  # Extract relevant information from each case
  extracted_case_data = extract_case_data.partial(execution_id=execution_id).expand(case_data=jsonl_data)

  # Prepare Bedrock input 
  prepare_input = prepare_bedrock_input.expand(case_data=extracted_case_data)

  # Invoke Amazon Bedrock with prepared inputs
  invoke_bedrock = BedrockInvokeModelOperator.partial(
      task_id="invoke_bedrock_task",
      model_id="anthropic.claude-3-haiku-20240307-v1:0",
      region_name="us-east-1"
  ).expand(input_data=prepare_input)

  # Process Bedrock output and prepare JSON for writing back to Salesforce
  processed_output = process_bedrock_output.expand(zipped_data=invoke_bedrock.output.zip(extracted_case_data))

  # Create S3 object with the relevant information
  create_s3_object = S3CreateObjectOperator.partial(
      task_id="create_s3_object",
      s3_bucket=S3_BUCKET_NAME
  ).expand_kwargs(
      generate_s3_key.expand(zipped_data=processed_output.zip(extracted_case_data))
  )

  # AWS Glue job to write data back to Salesforce.
  glue_job = GlueJobOperator(
      task_id="write-to-salesforce",
      job_name=f"{STACK_NAME}_write_salesforce_case_comments",
      script_location=f"s3://{S3_BUCKET_NAME}/glue/write_case_comments.py",
      s3_bucket=f"{S3_BUCKET_NAME}",
      iam_role_name=GLUE_IAM_ROLE,
      script_args={
          '--S3_BUCKET_NAME': S3_BUCKET_NAME,
          '--S3_PREFIX': S3_BEDROCK_PREFIX,
          '--CONNECTION_NAME': mwaa_config.SALESFORCE_CONNECTION,
          '--MWAA_EXECUTION_ID': str(execution_id)
      },        
      create_job_kwargs={"GlueVersion": "4.0", "NumberOfWorkers": 2, "WorkerType": "G.1X", "Connections": { "Connections": [GLUE_SFDC_CONNECTION_NAME] }, "ExecutionClass": "STANDARD", "ExecutionProperty": { "MaxConcurrentRuns": MAX_GLUE_JOB_CONCURRENCY } }
  )

#  Task to delete S3 object after we complete writing to SFDC.
  # delete_s3_object = S3DeleteObjectsOperator(
  #     task_id="delete_s3_key",
  #     bucket=S3_BUCKET_NAME
  # ).expand_kwargs(
  #     keys=s3_keys
  # )

  
  # Task dependencies
  trigger_glue_job >> s3_keys >> jsonl_data >> extracted_case_data >> prepare_input >> invoke_bedrock >> processed_output >> create_s3_object >> glue_job #>> delete_s3_object