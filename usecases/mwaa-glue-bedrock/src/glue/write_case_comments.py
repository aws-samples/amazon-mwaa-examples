import sys
import json
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue import DynamicFrame

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "S3_BUCKET_NAME", "S3_PREFIX", "CONNECTION_NAME", "MWAA_EXECUTION_ID"],
)
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

# Extract additinoal arguments
S3_BUCKET_NAME = args["S3_BUCKET_NAME"]
S3_PREFIX = args["S3_PREFIX"]
CONNECTION_NAME = args["CONNECTION_NAME"]
MWAA_EXECUTION_ID = args["MWAA_EXECUTION_ID"]

S3_PATH = f"s3://{S3_BUCKET_NAME}/{S3_PREFIX}/{MWAA_EXECUTION_ID}/"
logger = glueContext.get_logger()
logger.info(f"S3_PATH: {S3_PATH}")


# Script generated for node Amazon S3
AmazonS3_node1727343552793 = glueContext.create_dynamic_frame.from_options(
    format_options={"multiLine": "false"},
    connection_type="s3",
    format="json",
    connection_options={"paths": [S3_PATH], "recurse": True},
    transformation_ctx="AmazonS3_node1727343552793",
)

# Script generated for node Change Schema
ChangeSchema_node1727343555410 = ApplyMapping.apply(
    frame=AmazonS3_node1727343552793,
    mappings=[
        ("parentid", "string", "ParentId", "string"),
        ("commentbody", "string", "CommentBody", "string"),
        ("ispublished", "boolean", "IsPublished", "boolean"),
    ],
    transformation_ctx="ChangeSchema_node1727343555410",
)

# Script generated for node Salesforce
Salesforce_node1727343557676 = glueContext.write_dynamic_frame.from_options(
    frame=ChangeSchema_node1727343555410,
    connection_type="salesforce",
    connection_options={
        "apiVersion": "v60.0",
        "connectionName": CONNECTION_NAME,
        "entityName": "CaseComment",
        "writeOperation": "INSERT",
    },
    transformation_ctx="Salesforce_node1727343557676",
)

job.commit()
