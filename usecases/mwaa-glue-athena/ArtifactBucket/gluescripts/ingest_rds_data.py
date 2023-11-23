import boto3
import botocore
import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsgluedq.transforms import EvaluateDataQuality

#create glue context
args = getResolvedOptions(sys.argv, ["JOB_NAME","table_name","bucket_name"])
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)
s3_resource = boto3.resource('s3')

#fetch bucket and table name
table_name = args["table_name"]
bucket_name = args["bucket_name"]

#set key name to write data
key_name = 'dqrules/' + table_name


#read data from rds into glue dynamic frame
input_dyf = glueContext.create_dynamic_frame.from_options(
    connection_type="postgresql",
    connection_options={
        "useConnectionProperties": "true",
        "dbtable": "dms_sample." + table_name,
        "connectionName": "rds-pg",
    }
    )



#check if data quality rules exist for the table
try:
    s3_resource.Object(bucket_name, key_name).load()
except botocore.exceptions.ClientError as e:
    if e.response['Error']['Code'] == "404":
        print('DQ rules for this table does not exist')
        
#run data quality checks if rules exist for the dataset    
else:
    s3_client = boto3.client('s3')
    data = s3_client.get_object(Bucket=bucket_name, Key=key_name)
    EvaluateDataQuality_ruleset = data['Body'].read().decode('utf-8')
    
    EvaluateDataQualityMultiframe = EvaluateDataQuality().process_rows(
        frame=input_dyf,
        ruleset=EvaluateDataQuality_ruleset,
        publishing_options={
            "dataQualityEvaluationContext": "EvaluateDataQualityMultiframe",
            "enableDataQualityCloudWatchMetrics": True,
            "enableDataQualityResultsPublishing": True,
        },
        additional_options={"performanceTuning.caching": "CACHE_NOTHING"},
        )


#raise error if the job didnt pass all data quality checks
    assert (
        EvaluateDataQualityMultiframe[
            EvaluateDataQuality.DATA_QUALITY_RULE_OUTCOMES_KEY
            ].filter(lambda x: x["Outcome"] == "Failed").count() == 0
            ), "The job failed as it did not pass data quality rules"
            

#write dataset to s3 in csv format
input_dyf.toDF().write\
    .format("csv")\
    .option("quote", None,)\
    .option("header", True,)\
    .mode("overwrite")\
    .save("s3://" + bucket_name + "/raw/" + table_name +"/")
                    

job.commit()


                

