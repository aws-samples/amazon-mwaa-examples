# Deploy ECS and RDS Resources using CloudFormation
This sample project helps creating MWAA Sandbox environment on ECS Fargate 

## Deployment

### Prerequisites
- Existing MWAA Environment prerequisite steps [todo: add link]
- AWS CLI [todo: add link]

### Deploy the resources using CloudFormation template
Make sure you are on `../usecases/local-runner-onecs-fargate/cloudformation` folder . 

#### Step # 1 Prepare
Go to your favourite code editor and update the CloudFormation template input parameters in `./parameter-values.json` 

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
To clean up the resources created, run below command along with CF stack-name parameter

```
aws cloudformation delete-stack --stack-name mwaa-ecs-release
```