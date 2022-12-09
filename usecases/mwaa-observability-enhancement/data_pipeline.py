# DAG python file to execute workflow
#1. Wait for source data to be present in S3 bucket
#2. Run a glue crawler task to create the table metadata in the data catalog from the source data
#3. Run a glue job tasl to transform the source data into a processed data format while performing file format conversions
#4. Create a EMR cluster
#5. Run a EMR job to generate reporting data sets
#6. Terminate the EMR cluster


from datetime import timedelta
from distutils.command.config import config  
import airflow  
from airflow import DAG  
from airflow.providers.amazon.aws.sensors.s3_prefix import S3PrefixSensor
from airflow.providers.amazon.aws.operators.emr_create_job_flow import EmrCreateJobFlowOperator
from airflow.providers.amazon.aws.operators.emr_add_steps import EmrAddStepsOperator 
from airflow.providers.amazon.aws.operators.emr_terminate_job_flow import EmrTerminateJobFlowOperator
from airflow.providers.amazon.aws.sensors.emr_step import EmrStepSensor
from airflow.providers.amazon.aws.operators.glue import AwsGlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import AwsGlueCrawlerOperator

# Custom Operators deployed as Airflow plugins
from awsairflowlib.operators.aws_copy_s3_to_redshift import CopyS3ToRedshiftOperator

correlation_id = "{{ run_id }}"
S3_BUCKET_NAME = "airflow-testing"  
dag_name = "data_pipeline_workshop"  

default_args = {  
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': airflow.utils.dates.days_ago(1),
    'retries': 0,
    'retry_delay': timedelta(minutes=2),
    'provide_context': True,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False
}

dag = DAG(  
    dag_name,
    default_args=default_args,
    dagrun_timeout=timedelta(hours=2),
    schedule_interval='0 3 * * *'
)

s3_sensor = S3PrefixSensor(  
  task_id='s3_sensor',  
  bucket_name=S3_BUCKET_NAME,  
  prefix='data/raw/green',  
  dag=dag  
)

config = {"Name": "airflow-workshop-raw-green-crawler"}

glue_crawler = AwsGlueCrawlerOperator(
    task_id="glue_crawler",
    config=config,
    dag=dag)

task_id="glue_run_job"
glue_task = AwsGlueJobOperator(  
    task_id=task_id,  
    job_name='nyc_raw_to_transform',  
    iam_role_name='AWSGlueServiceRoleDefault',
    script_args={'--dag_name': dag_name,
                 '--task_id': task_id,
                 '--correlation_id': correlation_id},
    dag=dag)
  
emr_task_id="create_emr_cluster"

JOB_FLOW_OVERRIDES = {
    "Name": dag_name + "." + emr_task_id + "-" + correlation_id,
    "ReleaseLabel": "emr-5.29.0",
    "LogUri": "s3://{}/logs/emr/{}/{}/{}".format(S3_BUCKET_NAME, dag_name, emr_task_id, correlation_id), 
    "Instances": {
        "InstanceGroups": [
            {
                "Name": "Master nodes",
                "Market": "ON_DEMAND",
                "InstanceRole": "MASTER",
                "InstanceType": "m5.xlarge",
                "InstanceCount": 1
            },
            {
                "Name": "Slave nodes",
                "Market": "ON_DEMAND",
                "InstanceRole": "CORE",
                "InstanceType": "m5.xlarge",
                "InstanceCount": 2
            }
        ],
        "TerminationProtected": False,
        "KeepJobFlowAliveWhenNoSteps": True
    }
}

S3_URI = "s3://{}/scripts/emr/".format(S3_BUCKET_NAME)  

spark_task_id="add_steps"

SPARK_TEST_STEPS = [
   {
       'Name': 'setup - copy files',
       'ActionOnFailure': 'CANCEL_AND_WAIT',
       'HadoopJarStep': {
           'Jar': 'command-runner.jar',
           'Args': ['aws', 's3', 'cp', '--recursive', S3_URI, '/home/hadoop/']
       }
   },
   {
       'Name': 'Run Spark',
       'ActionOnFailure': 'CANCEL_AND_WAIT',
       'HadoopJarStep': {
           'Jar': 'command-runner.jar',
           'Args': ['spark-submit',
                    '/home/hadoop/nyc_aggregations.py',
                    's3://{}/data/transformed/green'.format(S3_BUCKET_NAME),
                    's3://{}/data/aggregated/green'.format(S3_BUCKET_NAME),
                     dag_name,
                     spark_task_id,
                     correlation_id]
       }
   }
]

cluster_creator = EmrCreateJobFlowOperator(
    task_id=emr_task_id,
    job_flow_overrides=JOB_FLOW_OVERRIDES,
    aws_conn_id='aws_default',
    emr_conn_id='emr_default',
    dag=dag
)

step_adder = EmrAddStepsOperator(
    task_id=spark_task_id,
    job_flow_id="{{ task_instance.xcom_pull('create_emr_cluster', key='return_value') }}",
    aws_conn_id='aws_default',
    steps=SPARK_TEST_STEPS,
    dag=dag
)

step_checker1 = EmrStepSensor(
    task_id='watch_step1',
    job_flow_id="{{ task_instance.xcom_pull('create_emr_cluster', key='return_value') }}",
    step_id="{{ task_instance.xcom_pull('add_steps', key='return_value')[0] }}",
    aws_conn_id='aws_default',
    dag=dag
)

step_checker2 = EmrStepSensor(
    task_id='watch_step2',
    job_flow_id="{{ task_instance.xcom_pull('create_emr_cluster', key='return_value') }}",
    step_id="{{ task_instance.xcom_pull('add_steps', key='return_value')[1] }}",
    aws_conn_id='aws_default',
    dag=dag
)

cluster_remover = EmrTerminateJobFlowOperator(
    task_id='remove_cluster',
    job_flow_id="{{ task_instance.xcom_pull('create_emr_cluster', key='return_value') }}",
    aws_conn_id='aws_default',
    dag=dag
)


s3_sensor >> glue_crawler >> glue_task >> cluster_creator >> step_adder >> step_checker1 >> step_checker2 >> cluster_remover