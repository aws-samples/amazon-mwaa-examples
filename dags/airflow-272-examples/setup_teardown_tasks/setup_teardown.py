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

import time
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

from datetime import datetime
from datetime import timedelta
import os
import json

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.models import Variable
from airflow.providers.amazon.aws.hooks.redshift_cluster import RedshiftHook

from airflow.providers.amazon.aws.operators.redshift_cluster import RedshiftCreateClusterOperator, RedshiftDeleteClusterOperator
from airflow.providers.amazon.aws.operators.redshift_data import RedshiftDataOperator
from airflow.providers.amazon.aws.sensors.redshift_cluster import RedshiftClusterSensor




default_args = {
    'owner': 'airflow',
    'start_date': days_ago(1),
    'depends_on_past': False
}

rs_username = Variable.get("rs_master_username")
rs_password = Variable.get("rs_master_password")


# Define the DAG
dag = DAG(
    'Setup_Teardown',
    description='DAG to connect to Redshift using psycopg2 getting credentials from AWS SecretsManager',
    schedule_interval=None,
    default_args=default_args,
    start_date=datetime(2023, 10, 11),
    catchup=False
)

create_cluster = RedshiftCreateClusterOperator(
    task_id="create_cluster",
    cluster_identifier="redshift-cluster-test",
    publicly_accessible=True,
    cluster_type="single-node",
    node_type="dc2.large",
    db_name="dev",
    master_username=rs_username,
    master_user_password=rs_password,
    aws_conn_id="aws_default",
    deferrable=True,
    dag=dag
)



wait_cluster_available = RedshiftClusterSensor(
        task_id="wait_cluster_available",
        cluster_identifier="redshift-cluster-test",
        target_status="available",
        aws_conn_id="aws_default",
        poke_interval=15,
        timeout=60 * 30,
        dag=dag
    )


# Create table in the cluster 
create_rs_table = RedshiftDataOperator(
        task_id="create_rs_table",
        cluster_identifier="redshift-cluster-test",
        database="dev",
        db_user="awsuser",
        aws_conn_id="aws_default",
        sql="""
            CREATE TABLE IF NOT EXISTS cities (
            cityid INTEGER,
            city VARCHAR NOT NULL,
            state VARCHAR NOT NULL
            );
        """,
        wait_for_completion=True,
        dag=dag
    )


# Load data into the table
insert_data = RedshiftDataOperator(
        task_id="insert_data",
        cluster_identifier="redshift-cluster-test",
        database="dev",
        db_user="awsuser",
        aws_conn_id="aws_default",
        sql="""
            INSERT INTO cities VALUES ( 1, 'Phoenix', 'Arizona');
            INSERT INTO cities VALUES ( 2, 'Arizona', 'Texas');
            INSERT INTO cities VALUES ( 3, 'Chicago', 'Illinois');
            INSERT INTO cities VALUES ( 4, 'Jacksonville', 'Florida');
            INSERT INTO cities VALUES ( 5, 'Boston', 'Massachusetts');
            INSERT INTO cities VALUES ( 6, 'Baltimore', 'Maryland');
        """,
        wait_for_completion=True,
        dag=dag
    )

# Query the data
task_query = RedshiftDataOperator(
        task_id='redshift_query',
        cluster_identifier='redshift-cluster-test',
        database='dev',
        db_user="awsuser",
        aws_conn_id="aws_default",
        sql=""" select * from dev.public.cities""",
        wait_for_completion=True,
        dag=dag
    )

# Delete a Redshift cluster
delete_cluster = RedshiftDeleteClusterOperator(
    task_id='delete_cluster',
    cluster_identifier='redshift-cluster-test',
    aws_conn_id="aws_default",
    deferrable=True,
    dag=dag
)

create_cluster >> wait_cluster_available >> create_rs_table >> insert_data >> task_query >> delete_cluster.as_teardown(setups=create_cluster)

