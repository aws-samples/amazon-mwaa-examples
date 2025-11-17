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

Required IAM Permissions:
- athena:StartQueryExecution - Execute Athena queries
- athena:GetQueryExecution - Get query execution status
- athena:GetQueryResults - Retrieve query results
- s3:GetObject - Read data from S3 for queries
- s3:PutObject - Write query results to S3
- glue:GetTable - Access Glue catalog tables
- cloudformation:CreateStack - Create CloudFormation stacks
- cloudformation:DeleteStack - Delete CloudFormation stacks
- cloudformation:DescribeStacks - Get stack status
"""
import os
from airflow.decorators import dag, task

from airflow.providers.amazon.aws.operators.athena import AthenaOperator
from datetime import datetime
from airflow.models.param import Param
from airflow.utils.trigger_rule import TriggerRule
from airflow.providers.amazon.aws.operators.cloud_formation import (
    CloudFormationCreateStackOperator,
    CloudFormationDeleteStackOperator,
)
from airflow.providers.amazon.aws.sensors.cloud_formation import (
    CloudFormationCreateStackSensor,
    CloudFormationDeleteStackSensor,
)

DAG_ID = "athena_dag"
cloudformation_stack_name = "covid-lake-stack"
template_url = "https://covid19-lake.s3.us-east-2.amazonaws.com/cfn/CovidLakeStack.template.json" 
cloudformation_create_parameters = {
    "StackName": cloudformation_stack_name,
    "TemplateURL": template_url,
    "TimeoutInMinutes": 2,
    "OnFailure": "DELETE", 
}

QUERY_1="""
SELECT 
  cases.fips, 
  admin2 as county, 
  province_state, 
  confirmed,
  growth_count, 
  sum(num_licensed_beds) as num_licensed_beds, 
  sum(num_staffed_beds) as num_staffed_beds, 
  sum(num_icu_beds) as num_icu_beds
FROM 
  "covid-19"."hospital_beds" beds, 
  ( SELECT 
      fips, 
      admin2, 
      province_state, 
      confirmed, 
      last_value(confirmed) over (partition by fips order by last_update) - first_value(confirmed) over (partition by fips order by last_update) as growth_count,
      first_value(last_update) over (partition by fips order by last_update desc) as most_recent,
      last_update
    FROM  
      "covid-19"."enigma_jhu" 
    WHERE 
      from_iso8601_timestamp(last_update) > now() - interval '200' day AND country_region = 'US') cases
WHERE 
  beds.fips = cases.fips AND last_update = most_recent
GROUP BY cases.fips, confirmed, growth_count, admin2, province_state
ORDER BY growth_count desc
"""
QUERY_2="""
SELECT * FROM "covid-19"."world_cases_deaths_testing" order by "date" desc limit 10;
"""

QUERY_3="""
SELECT 
   date,
   positive,
   negative,
   pending,
   hospitalized,
   death,
   total,
   deathincrease,
   hospitalizedincrease,
   negativeincrease,
   positiveincrease,
   sta.state AS state_abbreviation,
   abb.state 

FROM "covid-19"."covid_testing_states_daily" sta
JOIN "covid-19"."us_state_abbreviations" abb ON sta.state = abb.abbreviation
limit 500;
"""

@dag(
    dag_id = DAG_ID,
    start_date=datetime(2022, 1, 1),
    catchup=False,   
    schedule=None,
    params={
        "output_location": "s3://amzn-s3-demo-bucket/athena-results/"
    }    
)
def athena_dag():
    create_stack = CloudFormationCreateStackOperator(
        task_id="create_stack",
        stack_name=cloudformation_stack_name,
        cloudformation_parameters=cloudformation_create_parameters,
    )    

    wait_for_stack_create = CloudFormationCreateStackSensor(
        task_id="wait_for_stack_create",
        stack_name=cloudformation_stack_name,
    )

    query_1 = AthenaOperator(
        task_id="query_1",
        query=QUERY_1,
        database='default',
        output_location='{{ params.output_location }}',
    )

    query_2 = AthenaOperator(
        task_id="query_2",
        query=QUERY_2,
        database='default',
        output_location='{{ params.output_location }}',
    )

    query_3 = AthenaOperator(
        task_id="query_3",
        query=QUERY_3,
        database='default',
        output_location='{{ params.output_location }}',
    )

    delete_stack = CloudFormationDeleteStackOperator(
        task_id="delete_stack",
        stack_name=cloudformation_stack_name,
        trigger_rule=TriggerRule.ALL_DONE,
    )    

    wait_for_stack_delete = CloudFormationDeleteStackSensor(
        task_id="wait_for_stack_delete",
        stack_name=cloudformation_stack_name,
    )

    create_stack >> wait_for_stack_create >> query_1 >> delete_stack >> wait_for_stack_delete
    wait_for_stack_create >> query_2 >> delete_stack
    wait_for_stack_create >> query_3 >> delete_stack

athena_dag_instance = athena_dag()
