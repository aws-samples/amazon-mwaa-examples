# Lambda with MWAA

This example uses the [TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) dataset. This example deploys the following resources:

- Creates a repository called taxi_analysis and uploads a compiled image
- Creates a dynamic lambda function that uses the uploaded image and offloads tasks from an MWAA environment. The Airflow DAG invokes the dynamic lambda function and does a few aggregation on the dataset and stores the output in an S3 bucket that you create in your own account.

## Prerequisites:

Ensure that you have installed the following tools on your machine.

1. [aws cli](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
2. [Docker](https://docs.docker.com/get-docker/) installed on local machine
3. [Amazon Managed Workflows for Apache Airflow (Amazon MWAA)](https://aws.amazon.com/managed-workflows-for-apache-airflow/) environment
4. [Amazon S3 bucket](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html) to store the inputs and outputs of the processing. lets call this databucket
5. [A Lambda IAM execution role](https://aws.amazon.com/premiumsupport/knowledge-center/lambda-execution-role-s3-bucket/) to access the S3 bucket in 4. Note this role should have the following actions allowed in it's policy document "s3:List*", "s3:Put*", "s3:Get*", "s3:DeleteObject" "s3:DeleteObjectVersion" on the S3 bucket along with AWS manged AWSLambdaBasicExecutionRole policy. Lets call that role 'taxi_ride_analysis_lambda_execution_role'
- Sample policy 
```
  {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:List*",
                "s3:Put*",
                "s3:Get*",
                "s3:DeleteObject",
                "s3:DeleteObjectVersion"
            ],
            "Resource": [
                "arn:aws:s3:::{databucket}",
                "arn:aws:s3:::{databucket}/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"

            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "iam:PassedToService": "lambda.amazonaws.com"
                }
            }
        }
    ]
}
```
6. MWAA Execution role need permissions to create/delete Lambda functions
- Sample policy
```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "Lambda",
            "Effect": "Allow",
            "Action": [
                "lambda:CreateFunction",
                "lambda:InvokeFunction",
                "lambda:GetFunction",
                "lambda:GetFunctionConfiguration",
                "lambda:DeleteFunction"
            ],
            "Resource": "arn:aws:lambda:{region}:{account}:function:taxi_ride_analysis_lambda_execution_role"
        },
        {
            "Sid": "LambdaList",
            "Effect": "Allow",
            "Action": "lambda:ListFunctions",
            "Resource": "*"
        },
        {
            "Sid": "Passrole",
            "Effect": "Allow",
            "Action": "iam:Passrole",
            "Resource": "arn:aws:iam::{account}:role/taxi_ride_analysis*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:List*",
                "s3:Put*",
                "s3:Get*",
            ],
            "Resource": [
                "arn:aws:s3:::{databucket}",
                "arn:aws:s3:::{databucket}/*"
            ]
        }

    ]
}
```
_Note: If you do not have running Amazon Managed Workflows for Apache Airflow (Amazon MWAA) environment, deploy it from the root of the project using terraform or AWS Cloud Development Kit (AWS CDK).

## Build container image and upload to Amazon Elastic Container Registry (Amazon ECR)

Clone the repository

```sh
git clone https://github.com/aws-samples/amazon-mwaa-examples.git
```

Navigate the image directories and run `make` by passing your aws related related arguments (account and region)

```sh
cd blueprints/examples/Lambda/image
make ci REGION=us-east-2 ACCOUNT=123456789012
```
This step would 
 - build the taxi_analysis image 
 - tag the mage as latest
 - Create a new docker repository named taxi_analysis in the region that you have choosen
 - Update the repository with the Amazon Elastic Container Registry (Amazon ECR) policy defined in the file ecrpolicy.json
 - Push the image taxi_analysis:latest to the taxi_analysis ECR repo


If you have a Amazon Elastic Container Registry (Amazon ECR) repository already created, then you can run the following command. Do note to change all entries of `--repository-name taxi_analysis` in the makefile to your repository name `--repository-name my_own_repository`

```sh
cd blueprints/examples/Lambda/image
make update REGION=us-east-2 ACCOUNT=123456789012
cd ..
```

_Note: Your IAM user permission should have access to create a repository in Amazon Elastic Container Registry (Amazon ECR) in your choosen account and region.

## Login to Amazon Elastic Container Registry (Amazon ECR)
Login to your Amazon Elastic Container Registry (Amazon ECR) repository using the AWS console. You should see a new image in ECR with taxi_analysis:latest.

## Upload DAG files to S3
### 1. Upload DAG file to S3
Navigate to the dag folder

```sh
cd blueprints/examples/Lambda/dags
```
Make the following changes to the DAG file:

-  Line 12 in the DAG file and replace the S3Bucket field with your own S3 bucket name. This would be the bucket name as mentioned in prerequisites step 4. For example, if your databucket is called "my-custom-data-source-destination-bucket", then the line should look as :
    ```
    S3Bucket = "my-custom-data-source-destination-bucket"
    ```

-  Line 15 in the DAG file and replace the value of the ImageUri. The line should look as:
   ``` 
   'ImageUri': "<Your_AWS_Account_Number>.dkr.ecr.<Your_AWS_Region>.amazonaws.com/taxi_analysis:latest",
   ```
- Line 40 in the DAG dile and replace the value of the lambda_role with that created in Step 5 above. The line should look like
  ```
   lambda_role = f'arn:aws:iam::<Your_AWS_Account_Number>:role/taxi_ride_analysis_lambda_execution_role'
  ```

Upload all files inside the dag directory to your MWAA S3 bucket.
This will copy the necessary DAG file, requirements and custom libraries.

```sh
aws s3 cp dags  s3://mybucket/dags --recursive
```

Update the Amazon MWAA environment with the new requirements file
```sh
aws mwaa update-environment --name MWAA_Environment --requirements-s3-path dags/requirements/requirements.txt 
```
Update environment can take upto 20 minutes to complete. Checkout [MWAA local runner](https://github.com/aws/aws-mwaa-local-runner) for local testing and faster feedback while updating requirements and plugins.

## Login to Amazon Managed Workflows for Apache Airflow (Amazon MWAA)

Login to your Amazon Managed Workflows for Apache Airflow (Amazon MWAA) environment. 

You would see that there are 3 new DAGs: tripreport_fhv, tripreport_green and tripreport_yellow. Unpause any of the DAG and Run it from Airflow UI console.

### What does the DAG do

The DAG looks at the New York Taxi trip data available in https://d37ci6vzurychx.cloudfront.net/trip-data/ and creates 3 DAGs dynamically for each of the 3 taxi types fhv, yellow and green.
The Lambda function takes the data for each of these taxi types and does some aggregation functions on top of it. The final outputs in parquet format are stored in the S3 bucket, output directory.

High level architecture:

![Lambda Architecture](/examples/Lambda/LambdaArchitecture.png?raw=true "Lambda Architecture")

DAG Task dependency:

![DAG Task Dependencies](/examples/Lambda/DAGtasks.png?raw=true "DAG Task Dependencies")

### Cleanup

### Troubleshooting

1. "failed to solve with frontend dockerfile.v0: failed to create LLB definition"
    ```
    docker logout public.ecr.aws
    export DOCKER_BUILDKIT=0
    export COMPOSE_DOCKER_CLI_BUILD=0
    ```

