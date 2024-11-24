
# Event-Driven Data Integration Powered by Amazon Managed Workflows for Apache Airflow (MWAA)

## Overview
This project demonstrates how to optimize data integration workflows through [Amazon Managed Workflows for Apache Airflow (MWAA)](https://aws.amazon.com/mwaa/) by leveraging an event-driven architecture. The demonstration integrates [Amazon EventBridge](https://aws.amazon.com/eventbridge/) with Salesforce, consuming Salesforce platform events and publishing these as updates in Airflow Datasets via an [AWS Lambda](https://aws.amazon.com/lambda/) function. MWAA triggers a Directed Acyclic Graph (DAG) based on the event to process the data (a new support case).

When a new case is created in Salesforce, MWAA will extract relevant information and use [Amazon Bedrock](https://aws.amazon.com/bedrock/) to suggest a resolution. MWAA then writes the data back to Salesforce via an [AWS Glue](https://aws.amazon.com/glue/) job, including Bedrock's suggestion in the case comments.

## Prerequisites
1. **AWS Account**: You need an AWS user with sufficient privileges to create AWS resources, such as [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/), [Amazon S3](https://aws.amazon.com/s3/), [IAM Roles and Policies](https://aws.amazon.com/iam/), [AWS Glue](https://aws.amazon.com/glue/) connections and jobs, and [Amazon MWAA](https://aws.amazon.com/mwaa/) environments.
2. **Access to Amazon Bedrock (Claude 3 Haiku Model)**: Log in to [Amazon Bedrock Console](https://us-east-1.console.aws.amazon.com/bedrock/home#/modelaccess), navigate to Model Access, and grant access to Anthropic Claude 3 Haiku model.
3. **AWS CLI Installed and Configured**: [Install the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) if you haven’t already.
4. **AWS SAM installed**: [Install the AWS SAM](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) if you haven't already.
4. **Salesforce Account**: If you don't have one, sign up for a [Salesforce free trial](https://www.salesforce.com/form/signup/freetrial-sales/) or a [Salesforce developer account](https://developer.salesforce.com/signup). Once you have your account, note down your Org ID, which is the first part of your Salesforce domain (e.g., in `https://aws49-dev-ed.lightning.force.com/`, the Org ID is `aws49-dev-ed`).
5. **Install Salesforce CLI**: Follow [Salesforce CLI installation instructions](https://developer.salesforce.com/tools/salesforcecli).

## Deployment Prerequisites
For ease of use, we have automated the deployment steps. You can skip directly to the "Deployment" section below. However, for your understanding, here are the phases of deployment:

### Phase 1: Salesforce Connected App
To integrate with Salesforce, this solution requires a Salesforce Connected App with OAuth2 `client_credentials` and `authorization_code` flows.

### Phase 2: AWS Serverless Application Model (SAM)
The [AWS Serverless Application Model (SAM)](https://aws.amazon.com/serverless/sam/) template will deploy base resources such as [Amazon VPC](https://aws.amazon.com/vpc/) and networking, [Amazon S3](https://aws.amazon.com/s3/) buckets, the MWAA environment, and an AWS Lambda function to process Salesforce events. This phase depends on Phase 1 and requires the Salesforce URL, Connected App Consumer ID, and Consumer Secrets as inputs.

### Phase 3: MWAA DAG
This DAG (`src/dags/create_resources.py`) will be executed once through MWAA to create the post-[AWS CloudFormation](https://aws.amazon.com/cloudformation/) deployment resources. These include the Salesforce Event Relay, Amazon EventBridge partner source, Event Bus, and EventBridge Rule to intercept newly created Salesforce case events and add the AWS Lambda function as a target.

## Deployment
We have automated the deployment for ease of use.
Install python packages required: 
```bash
pip install -r requirements.txt
```

To deploy the solution, execute the following command:
```bash
python deploy.py <Salesforce_Org_Alias> <your_salesforce_Username_email> <aws_region_id>
```

Example: 
```bash
python deploy.py aws49-dev-ed john.doe@example.com us-west-1
```

## Post Deployment
Once all resources are deployed, you can create a new case in Salesforce. This action triggers a Salesforce Platform Event that is pushed to Amazon EventBridge. EventBridge routes this event to an AWS Lambda function, which pushes an update to MWAA Airflow Datasets, triggering the data pipeline DAG.
