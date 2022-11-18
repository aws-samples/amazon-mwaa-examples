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


import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from awsglue.transforms import Join
import json
## @params: [JOB_NAME]
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'DATA_BUCKET', 'YEARS'])
print("arguments", sys.argv)
data_bucket = args['DATA_BUCKET']
s3tgtpath=f"s3://{data_bucket}/curatedzone/weather_data"
years = json.loads(args["YEARS"])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# builds weather reading for US along with the weather station data and stores in parquet format.
weather_station_data = spark.read.format("csv")\
                    .option("sep"," ")\
                        .load(f"s3://{data_bucket}/rawzone/station_lookup.txt")
                         

for year in years :
    weather_data = glueContext.create_dynamic_frame.from_catalog(database = "default", table_name = f"year_{year}", transformation_ctx = "weather_data")
    

    weather_station_data.printSchema()

    dfstationssplit = weather_station_data.select(
        weather_station_data._c0.substr(1,11).alias('id'),
        weather_station_data._c0.substr(1,2).alias('countrycode'),
        weather_station_data._c0.substr(14,9).alias('lat'),
        weather_station_data._c0.substr(22,9).alias('long'),
        weather_station_data._c0.substr(39,2).alias('state')
    )
    dfstationssplit.createOrReplaceTempView("stations_sparkvw")
    weather_data.toDF().createOrReplaceTempView("readings_sparkvw")
    dfprocessed = spark.sql("select a.* ,b.countrycode , b.state from readings_sparkvw a, stations_sparkvw b where a.id = b.id and element ='PRCP' and b.countrycode ='US'")
    dfprocessed.write.mode("overwrite").format('parquet').save(s3tgtpath)

    job.commit()
