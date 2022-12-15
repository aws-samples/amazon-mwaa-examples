from datetime import timedelta  
import airflow  
from airflow import DAG  
from airflow.providers.amazon.aws.sensors.s3_key import S3KeySensor
from airflow.providers.amazon.aws.operators.s3_copy_object import S3CopyObjectOperator
from airflow.providers.amazon.aws.operators.emr_create_job_flow import EmrCreateJobFlowOperator
from airflow.providers.amazon.aws.operators.emr_add_steps import EmrAddStepsOperator 
from airflow.providers.amazon.aws.operators.emr_terminate_job_flow import EmrTerminateJobFlowOperator
from airflow.providers.amazon.aws.sensors.emr_step import EmrStepSensor
from airflow.providers.amazon.aws.operators.glue import AwsGlueJobOperator
from airflow.providers.amazon.aws.operators.glue_crawler import AwsGlueCrawlerOperator
import os
# Custom Operators deployed as Airflow plugins



execution_date = "{{ execution_date }}"  
  
JOB_FLOW_OVERRIDES = {
    "Name": "Data-Pipeline-" + execution_date,
    "ReleaseLabel": "emr-5.29.0",
    "LogUri": f"s3://{{{{ var.value.EMR_DATA_BUCKET }}}}/logs/emr/" ,
    "JobFlowRole": "EMR_EC2_DefaultRole",
    "ServiceRole": "EMR_DefaultRole_V2",
    "Tags": [ {
        "Key": "for-use-with-amazon-emr-managed-policies",
        "Value": "true"
    }],
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
 
SPARK_TEST_STEPS = [
   {
       'Name': 'setup - copy files',
       'ActionOnFailure': 'CANCEL_AND_WAIT',
       'HadoopJarStep': {
           'Jar': 'command-runner.jar',
           'Args': ['aws', 's3', 'cp', '--recursive', f"s3://{{{{ var.value.EMR_DATA_BUCKET }}}}/spark/emr/", '/home/hadoop/']
       }
   },
   {
       'Name': 'Run Spark',
       'ActionOnFailure': 'CANCEL_AND_WAIT',
       'HadoopJarStep': {
           'Jar': 'command-runner.jar',
           'Args': ['spark-submit',
                    '/home/hadoop/nyc_aggregations.py',
                    f's3://{{{{ var.value.EMR_DATA_BUCKET }}}}/rawzone/emr/nyc/green_tripdata_2020-06.csv',
                    f's3://{{{{ var.value.EMR_DATA_BUCKET }}}}/datazone/emr/nyc']
       }
   }
]
  
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
    'emr_sample',
    default_args=default_args,
    dagrun_timeout=timedelta(hours=2),
    schedule_interval='0 3 * * *'
)

s3_sensor = S3KeySensor(  
  task_id='s3_sensor',  
  bucket_name= "{{ var.value.EMR_DATA_BUCKET }}",  
  bucket_key='rawzone/emr/nyc/green_tripdata_2020-06.csv',  
  retries=2,
  timeout=60,
  poke_interval=20,
  dag=dag  
)
get_nyc_green_taxi_data = S3CopyObjectOperator(
    task_id="get_nyc_green_taxi_data",
    source_bucket_key='modules/f8fe356a07604a12bec0b5582be38aed/v1/data/green_tripdata_2020-06.csv',
    dest_bucket_key='rawzone/emr/nyc/green_tripdata_2020-06.csv',
    source_bucket_name='ee-assets-prod-us-east-1',
    dest_bucket_name= "{{ var.value.EMR_DATA_BUCKET }}",
    trigger_rule="all_failed",
    dag=dag 
)

cluster_creator = EmrCreateJobFlowOperator(
    task_id='create_emr_cluster',
    job_flow_overrides=JOB_FLOW_OVERRIDES,
    aws_conn_id='aws_default',
    emr_conn_id='aws_default',
    trigger_rule='one_success',
    dag=dag
)
step_adder = EmrAddStepsOperator(
    task_id='add_steps',
    job_flow_id="{{ ti.xcom_pull('create_emr_cluster', key='return_value') }}",
    aws_conn_id='aws_default',
    steps=SPARK_TEST_STEPS,
    dag=dag
)
step_checker = EmrStepSensor(
    task_id='watch_step',
    job_flow_id="{{ ti.xcom_pull('create_emr_cluster', key='return_value') }}",
    step_id="{{ ti.xcom_pull('add_steps', key='return_value')[0] }}",
    aws_conn_id='aws_default',
    dag=dag
)
cluster_remover = EmrTerminateJobFlowOperator(
    task_id='remove_cluster',
    job_flow_id="{{ ti.xcom_pull('create_emr_cluster', key='return_value') }}",
    aws_conn_id='aws_default',
    dag=dag
)

s3_sensor >> get_nyc_green_taxi_data 
s3_sensor >> cluster_creator
get_nyc_green_taxi_data >> cluster_creator >> step_adder >> step_checker >> cluster_remover