import json
from airflow import DAG
from airflow.providers.amazon.aws.operators.bedrock import BedrockInvokeModelOperator
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator, S3DeleteObjectsOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.decorators import task
from airflow.datasets import Dataset
from datetime import datetime, timedelta
import mwaa_config
import random, string

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

# Configure Dataset to consume
DATASET = Dataset(mwaa_config.SALESFORCE_OBJECT)

# Configure S3 bucket for outputs. 
S3_BUCKET_NAME = mwaa_config.BUCKET_NAME
S3_PREFIX = "output"

#Glue Connector details and job settings
GLUE_SFDC_CONNECTION_NAME = mwaa_config.SALESFORCE_CONNECTION
MAX_GLUE_JOB_CONCURRENCY = 5

#Glue execution role
GLUE_IAM_ROLE=mwaa_config.GLUE_EXECUTION_ROLE

# Get dataset updates
@task(inlets=[DATASET])
def get_dataset_updates(triggering_dataset_events=None):
    dataset_updates = []
    for dataset, dataset_list in triggering_dataset_events.items():
        for d in dataset_list:
            dataset_updates.append(d.extra)

    return dataset_updates

# Extract Salesforce event data from the JSON
@task
def extract_event_data(execution_id, event_data):
    # Extract relevant data from EventBridge event
    detail = event_data.get('detail', {}).get('payload', {})
    return {
        "ExecutionId": execution_id,
        "EventId": event_data.get('id'),
        "ParentId": detail.get('ChangeEventHeader', {}).get('recordIds', [])[0],
        "Subject": detail.get('Subject'),
        "Description": detail.get('Description'),
        "CaseNumber": detail.get('CaseNumber'),
        "Status": detail.get('Status'),
        "Priority": detail.get('Priority')
    }

@task
def generate_execution_id():
    # Extract relevant data from EventBridge event
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))


# Prepare the input for Amazon Bedrock
@task
def prepare_bedrock_input(event_info):
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
        case_number=event_info['CaseNumber'],
        subject=event_info['Subject'],
        status=event_info['Status'],
        priority=event_info['Priority'],
        description=event_info['Description']
    )

    return {
        "max_tokens": 4096,
        "anthropic_version": "bedrock-2023-05-31",
        "messages": [
            {
                "role": "user",
                "content": prompt, # You may consider adding a data chunking if the input text is too large.
            }
        ],
    }

@task
def process_bedrock_output(zipped_data):
    
    #Unzip
    bedrock_response, event_data = zipped_data
    print(f"Bedrock Response {bedrock_response}")
    print(f"Event Data {event_data}")

    # Convert the dictionary to a JSON string
    comment = bedrock_response['content'][0]['text']
    comment = f"Amazon Bedrock: {comment}"
    json_string = {
        "ParentId": event_data['ParentId'],
        "CommentBody": comment,
        "IsPublished": False,
        "IsDeleted": False
    }    
    json_string = json.dumps(json_string)

    # Encode the string to bytes
    return json_string

@task
def generate_s3_key(zipped_data):
    print(f"Zipped Data {zipped_data}")

    s3_body, event_data = zipped_data

    # Generating unique S3 object name
    execution_id = event_data.get("ExecutionId")
    parent_id = event_data.get("ParentId")
    return {
        "s3_key": f"{S3_PREFIX}/{execution_id}/{parent_id}.json",
        "data": s3_body
    }

with DAG(
    'process-salesforce-data',
    default_args=default_args,
    description='Process SFDC EventBridge CDC events and invoke Bedrock',
    schedule=[DATASET],
    start_date=datetime(2024, 9, 16),
    catchup=False,
) as dag:

    # Get dataset updates
    dataset_updates = get_dataset_updates()

    # Generate execution id
    execution_id = generate_execution_id()

    # Extract event information
    parsed_event = extract_event_data.partial(execution_id=execution_id).expand(event_data=dataset_updates)

    # Prepare Bedrock input 
    prepare_input = prepare_bedrock_input.expand(event_info=parsed_event)

    # Invoke Claude3.Haiku model through Amazon Bedrock
    invoke_bedrock = BedrockInvokeModelOperator.partial(
        task_id="invoke_bedrock_task",
        model_id="anthropic.claude-3-haiku-20240307-v1:0",
        region_name="us-east-1"
    ).expand(input_data=prepare_input)

    # Process Bedrock output
    processed_output = process_bedrock_output.expand(zipped_data=invoke_bedrock.output.zip(parsed_event))    

    # Create S3 object with relevant information from Bedrock and ParentId, so we can write the data back to Salesforce.
    create_s3_object = S3CreateObjectOperator.partial(
        task_id="create_s3_object",
        s3_bucket=S3_BUCKET_NAME, 
    ).expand_kwargs(
        generate_s3_key.expand(zipped_data=processed_output.zip(parsed_event))
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
            '--S3_PREFIX': S3_PREFIX,
            '--CONNECTION_NAME': mwaa_config.SALESFORCE_CONNECTION,
            '--MWAA_EXECUTION_ID': str(execution_id)
        },        
        create_job_kwargs={"GlueVersion": "4.0", "NumberOfWorkers": 2, "WorkerType": "G.1X", "Connections": { "Connections": [GLUE_SFDC_CONNECTION_NAME] }, "ExecutionClass": "STANDARD", "ExecutionProperty": { "MaxConcurrentRuns": MAX_GLUE_JOB_CONCURRENCY } }
    )

    # Task to delete S3 object after we complete writing to SFDC.
    # delete_s3_object = S3DeleteObjectsOperator.partial(
    #     task_id="delete_s3_key",
    #     bucket=S3_BUCKET_NAME
    # ).expand(
    #     keys=s3_key
    # )
    
    dataset_updates >> parsed_event >> prepare_input >> invoke_bedrock >> processed_output >> create_s3_object >> glue_job  #>> delete_s3_object