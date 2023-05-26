
# Welcome to your MWAA Cloudformation project!

Welcome to Amazon MWAA Blueprints !

This repository contains a collection of code that aim to make it easier and faster for customers to adopt Amazon MWAA. It can be used by AWS customers, partners, and internal AWS teams to configure and manage complete MWAA environment that are fully bootstrapped with the operational software that is needed to deploy and operate workloads.



## Getting Started

### Prerequisites

First, ensure that you have installed the following tools locally.

1. [aws cli](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
2. [MWAA deployer Permissions](https://docs.aws.amazon.com/mwaa/latest/userguide/access-policies.html#full-access-policy)

### Deployment Steps
1. To create MWAA environment with VPC with NAT/IGW
https://docs.aws.amazon.com/mwaa/latest/userguide/quick-start.html
2. To create MWAA environment with no NAT/IGW but with VPCEndpoints
    
    - Run the command below after replacing your_bucket_name with the S3 Bucket where DAGs are present
```
aws cloudformation create-stack --stack-name mwaa-environment-private-network --template-body file://template.yaml --parameters ParameterKey=S3Bucket,ParameterValue=your_bucket_name --capabilities CAPABILITY_IAM

```
### Cleanup
```
aws cloudformation delete-stack --stack-name mwaa-environment-private-network 
```