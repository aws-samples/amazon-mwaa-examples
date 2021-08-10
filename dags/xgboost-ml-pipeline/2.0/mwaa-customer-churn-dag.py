from __future__ import print_function
import json
import requests
import uuid
from datetime import datetime
import sys

# airflow operators
import airflow
from airflow.models import DAG
from airflow.utils.dates import days_ago
from airflow.operators.python_operator import PythonOperator

# airflow sagemaker operators
from airflow.providers.amazon.aws.operators.sagemaker_training import SageMakerTrainingOperator
from airflow.providers.amazon.aws.operators.sagemaker_endpoint import SageMakerEndpointOperator
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook

# boto3
import boto3

# sagemaker sdk
import sagemaker
from sagemaker.amazon.amazon_estimator import get_image_uri
from sagemaker.estimator import Estimator
from sagemaker.session import s3_input

# airflow sagemaker configuration
from sagemaker.workflow.airflow import training_config
from sagemaker.workflow.airflow import model_config_from_estimator
from sagemaker.workflow.airflow import deploy_config_from_estimator

# custom config
import config

#Create global unique identifier to make names unique
guid = uuid.uuid4().hex

#Create a unique name for the AWS Glue job and mwaa project to be created.
glue_job_name = config.GLUE_JOB_NAME_PREFIX+'-{}'.format(guid)

# =============================================================================
# functions
# =============================================================================

def preprocess_glue():
  """preprocess data using glue for etl"""

  # not best practice to hard code location 
  glue_script_location = 's3://{}/{}'.format(config.GLUE_JOB_SCRIPT_S3_BUCKET, config.GLUE_JOB_SCRIPT_S3_KEY)
  glue_client = boto3.client('glue')

  # instantiate the Glue ETL job
  response = glue_client.create_job(
    Name=glue_job_name,
    Description='PySpark job to extract the data and split in to training and validation data sets',
    Role=config.GLUE_ROLE_NAME,
    ExecutionProperty={
      'MaxConcurrentRuns': 2
    },
    Command={
      'Name': 'glueetl',
      'ScriptLocation': glue_script_location,
      'PythonVersion': '3'
    },
    DefaultArguments={
      '--job-language': 'python'
    },
    GlueVersion='1.0',
    WorkerType='Standard',
    NumberOfWorkers=2,
    Timeout=60
    )
  
  # execute the previously instantiated Glue ETL job
  response = glue_client.start_job_run(
    JobName=response['Name'],
    Arguments={
      '--S3_SOURCE': config.DATA_S3_SOURCE,
      '--S3_DEST': config.DATA_S3_DEST,
      '--TRAIN_KEY': 'train/',
      '--VAL_KEY': 'validation/' 
    }
  )


# must create a SageMaker team role that also has Glue access - must add this instruction in the blog
def get_sagemaker_role_arn(role_name, region_name):
    iam = boto3.client("iam", region_name=region_name)
    response = iam.get_role(RoleName=role_name)
    return response["Role"]["Arn"]

# =============================================================================
# setting up training, model creation and endpoint deployment configuration
# =============================================================================

# set configuration for tasks
hook = AwsBaseHook(aws_conn_id="airflow-sagemaker", client_type="sagemaker")
sess = hook.get_session(region_name=config.REGION_NAME) #how is this session different from the SageMaker session - necessary?
sagemaker_role = get_sagemaker_role_arn(config.SAGEMAKER_ROLE_NAME, config.REGION_NAME)
container = get_image_uri(sess.region_name, "xgboost")

# initialize training hyperparameters
hyperparameters = {
        "max_depth":"5",
        "eta":"0.2",
        "gamma":"4",
        "min_child_weight":"6",
        "subsample":"0.8",
        "objective":"binary:logistic",
        "num_round":"100"}

# create estimator
xgb_estimator = Estimator(
    image_name=container, 
    hyperparameters=hyperparameters,
    role=sagemaker_role,
    sagemaker_session=sagemaker.session.Session(sess),
    train_instance_count=1, 
    train_instance_type='ml.m5.4xlarge', 
    train_volume_size=5,
    output_path=config.SAGEMAKER_MODEL_S3_DEST
)

# create training inputs
sagemaker_taining_job_name=config.SAGEMAKER_TRAINING_JOB_NAME_PREFIX+'-{}'.format(guid)
sagemaker_training_data = s3_input(config.SAGEMAKER_TRAINING_DATA_S3_SOURCE, content_type=config.SAGEMAKER_CONTENT_TYPE)
sagemaker_validation_data = s3_input(config.SAGEMAKER_VALIDATION_DATA_S3_SOURCE, content_type=config.SAGEMAKER_CONTENT_TYPE)
sagemaker_training_inputs = {'train': sagemaker_training_data,
          'validation': sagemaker_validation_data}

# train_config specifies SageMaker training configuration
training_config = training_config(
  estimator=xgb_estimator, 
  inputs = sagemaker_training_inputs,
  job_name=sagemaker_taining_job_name
)

sagemaker_model_name=config.SAGEMAKER_MODEL_NAME_PREFIX+'-{}'.format(guid)
sagemaker_endpoint_name=config.SAGEMAKER_ENDPOINT_NAME_PREFIX+'-{}'.format(guid)

# endpoint_config specifies SageMaker endpoint configuration
endpoint_config = deploy_config_from_estimator(
  estimator=xgb_estimator, 
  task_id="train", 
  task_type="training", 
  initial_instance_count=1, 
  instance_type="ml.m4.xlarge",
  model_name=sagemaker_model_name,
  endpoint_name=sagemaker_endpoint_name
)

# =============================================================================
# define airflow DAG and tasks
# =============================================================================

# define airflow DAG

args = {"owner": "airflow", "start_date": airflow.utils.dates.days_ago(2), 'depends_on_past': False}

with DAG(
    dag_id=config.AIRFLOW_DAG_ID,
    default_args=args,
    start_date=days_ago(2),
    schedule_interval=None,
    concurrency=1,
    max_active_runs=1,
) as dag:
    process_task = PythonOperator(
      task_id="process",
      dag=dag,
      #provide_context=False,
      python_callable=preprocess_glue,
    )

    train_task = SageMakerTrainingOperator(
      task_id = "train",
      config = training_config,
      aws_conn_id = "airflow-sagemaker",
      wait_for_completion = True,
      check_interval = 60, #check status of the job every minute
      max_ingestion_time = None, #allow training job to run as long as it needs, change for early stop
    )

    endpoint_deploy_task = SageMakerEndpointOperator(
      task_id = "endpoint-deploy",
      config = endpoint_config,
      aws_conn_id = "sagemaker-airflow",
      wait_for_completion = True,
      check_interval = 60, #check status of endpoint deployment every minute
      max_ingestion_time = None,
      operation = 'create', #change to update if you are updating rather than creating an endpoint
    )

    # set the dependencies between tasks
    process_task >> train_task >> endpoint_deploy_task