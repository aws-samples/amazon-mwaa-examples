'''
MIT No Attribution

Copyright <YEAR> <COPYRIGHT HOLDER>

Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify,
merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
'''

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext

## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME','dag_name','task_id','correlation_id'])



sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

logger = glueContext.get_logger()
correlation_id = args['dag_name'] + "." + args['task_id'] + " " + args['correlation_id']
logger.info("Correlation ID from GLUE job: " + correlation_id)

## @type: DataSource
## @args: [database = "default", table_name = "green", transformation_ctx = "datasource0"]
## @return: datasource0
## @inputs: []
datasource0 = glueContext.create_dynamic_frame.from_catalog(database = "default", table_name = "green", transformation_ctx = "datasource0")
logger.info("After create_dynamic_frame.from_catalog: " + correlation_id )

## @type: ApplyMapping
## @args: [mapping = [("vendorid", "long", "vendorid", "long"), ("lpep_pickup_datetime", "string", "lpep_pickup_datetime", "string"), ("lpep_dropoff_datetime", "string", "lpep_dropoff_datetime", "string"), ("store_and_fwd_flag", "string", "store_and_fwd_flag", "string"), ("ratecodeid", "long", "ratecodeid", "long"), ("pulocationid", "long", "pulocationid", "long"), ("dolocationid", "long", "dolocationid", "long"), ("passenger_count", "long", "passenger_count", "long"), ("trip_distance", "double", "trip_distance", "double"), ("fare_amount", "double", "fare_amount", "double"), ("extra", "double", "extra", "double"), ("mta_tax", "double", "mta_tax", "double"), ("tip_amount", "double", "tip_amount", "double"), ("tolls_amount", "double", "tolls_amount", "double"), ("ehail_fee", "string", "ehail_fee", "string"), ("improvement_surcharge", "double", "improvement_surcharge", "double"), ("total_amount", "double", "total_amount", "double"), ("payment_type", "long", "payment_type", "long"), ("trip_type", "long", "trip_type", "long")], transformation_ctx = "applymapping1"]
## @return: applymapping1
## @inputs: [frame = datasource0]
applymapping1 = ApplyMapping.apply(frame = datasource0, mappings = [("vendorid", "long", "vendorid", "long"), ("lpep_pickup_datetime", "string", "lpep_pickup_datetime", "string"), ("lpep_dropoff_datetime", "string", "lpep_dropoff_datetime", "string"), ("store_and_fwd_flag", "string", "store_and_fwd_flag", "string"), ("ratecodeid", "long", "ratecodeid", "long"), ("pulocationid", "long", "pulocationid", "long"), ("dolocationid", "long", "dolocationid", "long"), ("passenger_count", "long", "passenger_count", "long"), ("trip_distance", "double", "trip_distance", "double"), ("fare_amount", "double", "fare_amount", "double"), ("extra", "double", "extra", "double"), ("mta_tax", "double", "mta_tax", "double"), ("tip_amount", "double", "tip_amount", "double"), ("tolls_amount", "double", "tolls_amount", "double"), ("ehail_fee", "string", "ehail_fee", "string"), ("improvement_surcharge", "double", "improvement_surcharge", "double"), ("total_amount", "double", "total_amount", "double"), ("payment_type", "long", "payment_type", "long"), ("trip_type", "long", "trip_type", "long")], transformation_ctx = "applymapping1")
logger.info("After ApplyMapping: " + correlation_id)

## @type: ResolveChoice
## @args: [choice = "make_struct", transformation_ctx = "resolvechoice2"]
## @return: resolvechoice2
## @inputs: [frame = applymapping1]
resolvechoice2 = ResolveChoice.apply(frame = applymapping1, choice = "make_struct", transformation_ctx = "resolvechoice2")
logger.info("After ResolveChoice: " + correlation_id)

## @type: DropNullFields
## @args: [transformation_ctx = "dropnullfields3"]
## @return: dropnullfields3
## @inputs: [frame = resolvechoice2]
dropnullfields3 = DropNullFields.apply(frame = resolvechoice2, transformation_ctx = "dropnullfields3")
logger.info("After DropNullFields: " + correlation_id)

## @type: DataSink
## @args: [connection_type = "s3", connection_options = {"path": "s3://airflow-yourname-bucket/data/transformed/green"}, format = "parquet", transformation_ctx = "datasink4"]
## @return: datasink4
## @inputs: [frame = dropnullfields3]
datasink4 = glueContext.write_dynamic_frame.from_options(frame = dropnullfields3, connection_type = "s3", connection_options = {"path": "s3://{{S3_BUCKET_NAME}}/data/transformed/green"}, format = "parquet", transformation_ctx = "datasink4")
logger.info("After write_dynamic_frame.from_options: " + correlation_id)

job.commit()