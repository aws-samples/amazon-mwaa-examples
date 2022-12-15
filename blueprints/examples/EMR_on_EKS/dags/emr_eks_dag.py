
"""
This is an example dag for an Amazon EMR on EKS Spark job.
"""
import os
from datetime import timedelta


from airflow import DAG
from airflow.providers.amazon.aws.operators.emr_containers import EMRContainerOperator
from airflow.utils.dates import days_ago
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.operators.s3_copy_object import S3CopyObjectOperator

# [START howto_operator_emr_eks_env_variables]
JOB_ROLE_ARN = os.getenv("JOB_ROLE_ARN", "arn:aws:iam::526021349079:role/EMRContainers-MWAA-role")


RAW_ZONE_PREFIX = "rawzone/emreks"

# [START howto_operator_emr_eks_config]
JOB_DRIVER_ARG = {
    "sparkSubmitJobDriver": {
        "entryPoint": f"s3://{{{{ var.value.DATA_BUCKET }}}}/spark/emreks/etl.py",
        "entryPointArguments": [f"s3://{{{{ var.value.DATA_BUCKET }}}}/", RAW_ZONE_PREFIX],
        "sparkSubmitParameters": "--conf spark.executors.instances=1 --conf spark.executors.memory=2G --conf spark.executor.cores=1 --conf spark.driver.cores=1",  # noqa: E501
    }
}

CONFIGURATION_OVERRIDES_ARG = {
    "applicationConfiguration": [
        {
            "classification": "spark-defaults",
            "properties": {
                "spark.hadoop.hive.metastore.client.factory.class": "com.amazonaws.glue.catalog.metastore.AWSGlueDataCatalogHiveClientFactory",  # noqa: E501
            },
        }
    ],
    "monitoringConfiguration": {
        "cloudWatchMonitoringConfiguration": {
            "logGroupName": "/aws/emr-eks-spark", #loggroup should exist. If not, provide createLogGroup permission in JOB_ROLE_ARN
            "logStreamNamePrefix": "airflow",
        }
    },
}



def get_failure_reasons(cluster_id):
    import boto3
    import json
    client = boto3.client('emr-containers') 
    response = client.list_job_runs(
        virtualClusterId= cluster_id,
        states=[
            'FAILED'
        ] 
    )
    print(json.dumps(response,indent=4, sort_keys=True, default=str))

with DAG(
    dag_id='emr_eks_weatherstation_job',
    dagrun_timeout=timedelta(hours=2),
    start_date=days_ago(1),
    schedule_interval=None,
    tags=["emr_containers", "example"],
) as dag:


    get_weather_station_data = S3CopyObjectOperator(
            task_id="weather_station_data",

            source_bucket_key='csv.gz/2011.csv.gz',
            dest_bucket_key=f'{RAW_ZONE_PREFIX}/weather_station_data.csv.gz',
            source_bucket_name='noaa-ghcn-pds',
            dest_bucket_name= '{{ var.value.DATA_BUCKET }}'
    )
    get_weather_station_lookup_data = S3CopyObjectOperator(
            task_id="weather_station_lookup_data",
            source_bucket_key ='ghcnd-stations.txt',
            dest_bucket_key =f'{RAW_ZONE_PREFIX}/station_lookup.txt',
            source_bucket_name ='noaa-ghcn-pds',
            dest_bucket_name = '{{ var.value.DATA_BUCKET }}'
    )


    job_starter = EMRContainerOperator(
        task_id="start_job",
        virtual_cluster_id="{{ var.value.EMR_VIRTUAL_CLUSTER_ID }}",
        execution_role_arn= "{{ var.value.JOB_ROLE_ARN }}",
        release_label="emr-6.3.0-latest",
        job_driver=JOB_DRIVER_ARG,
        configuration_overrides=CONFIGURATION_OVERRIDES_ARG,
        name="emr_eks_weatherstation_job",
    )
    show_failure = PythonOperator (
        task_id="get_failure_reasons_task",
        python_callable = get_failure_reasons,
        op_kwargs={"cluster_id":"{{ var.value.EMR_VIRTUAL_CLUSTER_ID }}"},
        trigger_rule = "all_failed"
    )

     
    get_weather_station_data >> job_starter
    get_weather_station_lookup_data >> job_starter
    job_starter >> show_failure


