# Deploy ECS and RDS Resources using CloudFormation
This sample project helps creating MWAA Sandbox environment on ECS Fargate 

## Deployment

### Prerequisites
- This tutorial assumes you have an existing Amazon MWAA environment and wish to create a development container with a similar configuration. If you do not, please see the [Virtual Private Cloud (VPC)](https://docs.aws.amazon.com/mwaa/latest/userguide/vpc-create.html), [execution role](https://docs.aws.amazon.com/mwaa/latest/userguide/mwaa-create-role.html), and managing environments ([dags, plugins, and requirements](https://docs.aws.amazon.com/mwaa/latest/userguide/working-dags.html)) sections of the MWAA documentation.
- Docker on your local desktop.
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html)

### Deploy the resources using CloudFormation template
Make sure you are on `../usecases/local-runner-onecs-fargate/cloudformation` folder . 

#### Step # 1 Prepare
Update the CloudFormation template input parameters file  `./parameter-values.json` with values of your MWAA Environment network parameter values using your favourite code editor

```
{
    "Parameters": {
        "VpcId": "vpc-your-mwaa-vpc-id",
        "ECRImageURI" : "123456789.dkr.ecr.us-east-1.amazonaws.com/mwaa-local-runner:latest",
        "SecurityGroups" : "sg-security-group-id",
        "PrivateSubnetIds" : "subnet-mwaapvtsubnetid1,subnet-mwaapvtsubnetid2",
        "PublicSubnetIds" : "subnet-mwaapublicsubnetid1,subnet-mwaapublicsubnetid2",
        "S3BucketURI" : "s3://your-mwaa-bucket-path",
        "ECSTaskExecutionRoleArn": "arn:aws:iam::123456789:role/service-role/mwaaExecutionRoleName",
        "AssignPublicIpToTask" : "yes"
    }
}
```
where...
- VpcId - your MWAA environment VpcID
- ECRImageURI - AWS ECR Image Repo URI you completed in previous step
- Securitygroups - security group or comma seperated security group ids if multiple e.g. [sg-group-id-1,sg-group-id-2]
- PrivateSubnetIds - Private Subnet Ids especially for RDS from your mwaa environment creation stack e.g. [pvt-subnet-id-1,pvt-subnet-id-2]
- PublicSubnetIds - Public Subnet Ids especially if need publicly accessible load balancer e.g. [public-subnet-id-1,public-subnet-id-2]
- S3BucketURI - The S3 path to the requirements e.g. s3://my-airflow-bucket
- ECStaskExecutionRoleArn - The task execution role ARN. If making use of the same role being used for the existing MWAA environment, make sure it has permissions to access ECR and CloudWatch e.g. arn:aws:iam::123456789:role/service-role/MwaaExecutionRole

#### Step # 2 Deploy CF template
Deploy the CloudFormation Template `./mwaa-on-ecs-fargate.yml` 

```
$ aws cloudformation deploy --stack-name mwaa-ecs-sandbox \ 
                            --template-file mwaa-on-ecs-fargate.yml \
                            --parameter-overrides file://parameter-values-test.json \ 
                            --capabilities CAPABILITY_IAM
```
#### Step # 2 Test Validate the deployment

It will take some time, be patience! Meanwhile monitor the resource creation at your AWS Console --> CloudFormation --> Stacks --> mwaa-ecs-sandbox 

Once Deployment is completed successfully, copy Load Balancer URL (internal or public as per input parameters you provided to template) and test validate the application


### Clean up
To clean up the resources created, run below command along with CF stack-name. Replace stack name parameter if different.

```
aws cloudformation delete-stack --stack-name mwaa-ecs-sandbox
```