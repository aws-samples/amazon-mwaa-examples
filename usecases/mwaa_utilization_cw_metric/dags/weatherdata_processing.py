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
This is an example dag orchestrating Glue Job.
"""
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.utils.dates import days_ago
from airflow.operators.python_operator import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.operators.s3_copy_object import S3CopyObjectOperator
from airflow.providers.amazon.aws.operators.glue_crawler import AwsGlueCrawlerOperator
import os
from airflow.models import Variable
from airflow.utils.task_group import TaskGroup
from airflow.providers.amazon.aws.operators.glue import AwsGlueJobOperator
# [START howto_operator_emr_eks_env_variables]
import json
RAW_ZONE_PREFIX = "rawzone"
DATA_BUCKET = Variable.get("DATA_BUCKET")
GLUE_SERVICE_ROLE_ARN = Variable.get("GLUE_SERVICE_ROLE_ARN")
GLUE_SERVICE_ROLE_NAME = Variable.get("GLUE_SERVICE_ROLE_NAME")

default_args = {
    'owner': 'Airflow',
    'depends_on_past': False,
    'catchup': False,
    'start_date': datetime(2022, 1, 1),
    'retries': 3,
    'retry_delay': timedelta(minutes=1)
}
config = {
        "Name": "noaa-weather-station-data", 
        "Role":GLUE_SERVICE_ROLE_ARN,
        "DatabaseName": "default",
        "Targets":
            {"S3Targets":[{"Path":f"s3://{DATA_BUCKET}/{RAW_ZONE_PREFIX}/"}]},
        "Configuration": "{\"Version\": 1.0,\"Grouping\": {\"TableGroupingPolicy\": \"CombineCompatibleSchemas\" } }"
    }


with DAG(
    dag_id="noaa_weather_station_data",
    schedule_interval=None,
    default_args=default_args,
) as dag:

    YEARS=["2010","2011","2012","2013","2014","2015","2016","2017","2018","2019","2020","2021","2022"]
    # YEARS=["2015","2016"]

    get_weather_station_lookup_data = S3CopyObjectOperator(
            task_id="weather_station_lookup_data",
            source_bucket_key ='ghcnd-stations.txt',
            dest_bucket_key =f'{RAW_ZONE_PREFIX}/station_lookup.txt',
            source_bucket_name ='noaa-ghcn-pds',
            dest_bucket_name = '{{ var.value.DATA_BUCKET }}'
    )
    with TaskGroup("weather_data", tooltip="Tasks for getting climatology data") as weather_data:

        for year in YEARS:
            ## This task will also increase the memory utilization because of the file size.
            get_weather_station_data = S3CopyObjectOperator(
                    task_id=year,
                    # source_bucket_key=f'csv.gz/{year}.csv.gz', Using csv so I can simulate auto scaling
                    source_bucket_key=f'csv/by_year/{year}.csv',
                    dest_bucket_key=f'{RAW_ZONE_PREFIX}/year={year}/data.csv',
                    source_bucket_name='noaa-ghcn-pds',
                    dest_bucket_name= '{{ var.value.DATA_BUCKET }}'
            )
  

    glue_crawler = AwsGlueCrawlerOperator(
            task_id="create_weather_reading_table",
            config=config,
    )
    glue_task = AwsGlueJobOperator(  
        task_id="build_dataUS_parquet",  
        job_name='noaa_weatherdata_transform',
        script_location=f"s3://{DATA_BUCKET}/scripts/noaa_weatherdata_transform.py",
        iam_role_name= GLUE_SERVICE_ROLE_NAME,  
        concurrent_run_limit=2,
        retry_limit=1,
        s3_bucket=f"s3://{DATA_BUCKET}/logs/gluejob/",
        script_args={   
                '--DATA_BUCKET': DATA_BUCKET,
                '--YEARS': json.dumps(YEARS)
            },
        create_job_kwargs= {
            "GlueVersion":"3.0"
        }
    ) 
    
    get_weather_station_lookup_data >> glue_crawler
    weather_data >> glue_crawler
    glue_crawler >> glue_task



