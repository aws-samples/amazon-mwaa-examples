import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job

#create glue context
args = getResolvedOptions(sys.argv, ["JOB_NAME","table_name","bucket_name"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

#fetch bucket and table name
bucket_name = args["bucket_name"]
table_name = args["table_name"]




#read raw data in csv format from s3 
input_df = spark.read.format("csv")\
    .option("header", "true")\
    .option("inferSchema", "true")\
    .load("s3://" + bucket_name + "/raw/" + table_name +"/")

#write curated data in parquet formatto s3 
input_df.write\
    .format("parquet")\
    .mode("overwrite")\
    .save("s3://" + bucket_name + "/curated/" + table_name +"/")
