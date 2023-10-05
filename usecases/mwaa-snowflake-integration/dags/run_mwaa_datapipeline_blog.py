import os, logging, boto3, zipfile
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.providers.snowflake.operators.snowflake import SnowflakeOperator
from airflow.providers.snowflake.transfers.s3_to_snowflake import S3ToSnowflakeOperator
from airflow.operators.python_operator import PythonOperator
from airflow.operators.dummy_operator import DummyOperator
from datetime import datetime, timedelta
from io import BytesIO
from airflow.providers.amazon.aws.operators.sns import SnsPublishOperator
from airflow.models import Variable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
now = datetime.now()

#Source and destination buckets and object keys
#Source files are stored as .zip
SRC_BUCKET = 'tripdata'
DEST_BUCKET=Variable.get("destination_bucket")
target_sns_arn=Variable.get("target_sns_arn")

#Snowflake table/stage and view defination
table='citibike_tbl'
stage='mwaa_citibike_stg'
view='citibike_vw'
#Snowflake queries
create_tbl = "create OR replace table " + table + " (ride_id TEXT,rideable_type TEXT,started_at TEXT,ended_at TEXT,start_station_name TEXT,start_station_id TEXT,end_station_name TEXT,end_station_id TEXT,start_lat TEXT,start_lng TEXT,end_lat TEXT,end_lng TEXT,member_casual TEXT)"
create_view = "create or replace materialized view " + view + " as select ride_id,rideable_type,to_timestamp_tz(started_at) starttime,to_timestamp_tz(ended_at) endtime,start_station_name,start_station_id,end_station_name,end_station_id,start_lat::float startlat,start_lng::float startlon,end_lat::float endlat,end_lng::float endlon,member_casual from " + table + " where started_at not like 'started_at';"
top_start_station_query="select start_station_name,count(start_station_name) c from " + view + " group by start_station_name order by c desc limit 10"
top_end_station_query="select end_station_name,count(end_station_name) c from " + view + " group by end_station_name order by c desc limit 10"

DEFAULT_ARGS = {
    'owner': 'airflow',
    'snowflake_conn_id': 'snowflake_conn_accountadmin',
    'depends_on_past': False,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
    'start_date': datetime(now.year,now.month,now.day,now.hour),
    'retries': 3,
    'retry_delay': timedelta(minutes=1),
}

def copy_and_unzip_s3(**context):
    logging.info (context['srcbucket'])
    logging.info (context['srckey'])
    logging.info (context['destbucket'])
    logging.info (context['destkey'])
    s3_resource = boto3.resource('s3')
    zip_obj = s3_resource.Object(bucket_name=context['srcbucket'], key=context['srckey'])
    buffer = BytesIO(zip_obj.get()["Body"].read())
    z = zipfile.ZipFile(buffer)
    logging.info('downloaded zip {}, zipObj {}'.format(z, zipfile))
    for filename in z.namelist():
        if filename.startswith("__") :
          continue
        file_info = z.getinfo(filename)
        logging.info('Interating over zip {}, zipObj {}'.format(filename, file_info))
        try:
            response = s3_resource.meta.client.upload_fileobj(
                z.open(filename),
                Bucket=context['destbucket'],
                Key=context['destkey']
            )
            logging.info('uploaded to s3 {}'.format(filename))
        except Exception as e:
            print(e)

def list_bucket(**context):
    conn = boto3.client('s3')
    for key in conn.list_objects(Bucket=context['destbucket'])['Contents']:
        if '.csv' in key['Key']:
            logging.info(key['Key'])

with DAG(
    dag_id=os.path.basename(__file__).replace(".py", ""),
    default_args=DEFAULT_ARGS,
    dagrun_timeout=timedelta(hours=2),
    schedule_interval=None,
    tags=['Snowflake','Citibike','DAG3'],
) as dag:

  start = DummyOperator(
    task_id='start'
  )

  end = DummyOperator(
    task_id='end'
  )

  #List the contents of the destination bucket after unzipping the files
  listBucket = PythonOperator(
    task_id='list_transformed_files',
    python_callable=list_bucket,
    op_kwargs={'destbucket': DEST_BUCKET}
  )

  #Scan through the dataset in the source bucket, unzip each file and store it in the destination bucket
  citibike_csvs=[]
  #Loop through the S3 files
  conn = boto3.client('s3')
  for key in conn.list_objects(Bucket=SRC_BUCKET)['Contents']:
    #if '.zip' in key['Key']:
    if key['Key'].startswith("2023") or key['Key'].startswith("2022"):
        key1 = (key['Key'])
        key2 = key1.replace('.zip','')
        key2 = key2.strip()
        SRC_KEY = str(key1)
        DEST_KEY = str(key2)
        citibike_csvs.append(str(key2))
        copyAndTransformS3File = PythonOperator(
            task_id='copy_and_unzip_s3_' + str(str(key1)),
            python_callable=copy_and_unzip_s3,
            op_kwargs={'srcbucket': SRC_BUCKET, 'srckey': SRC_KEY, 'destbucket': DEST_BUCKET, 'destkey': DEST_KEY},
        )

        start >> copyAndTransformS3File >> listBucket


  #Create a table in snowflake based on the dataset
  createTable = SnowflakeOperator(
        task_id="create_table",
        sql=create_tbl
  )    

  listBucket >> createTable

  #Create a view (a query that sits on top of a table) in snowflake 
  createView = SnowflakeOperator(
    task_id="create_view",
    sql=create_view
  )

  #After unzipping the files, copy the files into the snowflake table created
  k=1
  for j in citibike_csvs:
   copy_into_table = S3ToSnowflakeOperator(
      task_id='copy_into_table_' + str(j),
      s3_keys=[j], 
      table=table,
      stage=stage,
      file_format="(type = 'CSV',field_delimiter = ',',field_optionally_enclosed_by='\"')"
  )
   k=k+1 
   createTable >> copy_into_table >> createView

  #Run queries on the View created
  topStationsStart = SnowflakeOperator(
    task_id='top_start_stations',
    sql=top_start_station_query
  )
  
  topStationsDestination = SnowflakeOperator(
    task_id='top_destination_stations',
    sql=top_end_station_query
  )

  snsTask1 = SnsPublishOperator(
        task_id='query1_result_to_sns',
        target_arn=target_sns_arn,
        subject='Top start stations',
        message="{{ task_instance.xcom_pull('top_start_stations', key='return_value')}}",
        aws_conn_id="aws_default"
  )

  snsTask2 = SnsPublishOperator(
        task_id='query2_result_to_sns',
        target_arn=target_sns_arn,
        subject='Top destination stations',
        message="{{ task_instance.xcom_pull('top_destination_stations', key='return_value')}}",
        aws_conn_id="aws_default"
  )

  createView >> topStationsStart >> topStationsDestination >> snsTask1 >> snsTask2 >> end
