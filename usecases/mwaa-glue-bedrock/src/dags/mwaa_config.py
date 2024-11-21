from airflow.models import Variable
import os, json

mwaa_vars = json.loads(Variable.get("mwaa"))

BUCKET_NAME = mwaa_vars.get('artifactBucket')
GLUE_EXECUTION_ROLE = mwaa_vars.get('glueExecutionRole')
STACK_NAME = mwaa_vars.get("stackName")

SALESFORCE_CONNECTION = "salesforce_connection"
SALESFORCE_OBJECT = "CaseChangeEvent"
REGION=os.getenv("AWS_DEFAULT_REGION")

