## Disclaimer

AWS code samples are example code that demonstrates practical implementations of AWS services for specific use cases and scenarios.

These application solutions are not supported products in their own right, but educational examples to help our customers use our products for their applications. As our customer, any applications you integrate these examples into should be thoroughly tested, secured, and optimized according to your business's security standards & policies before deploying to production or handling production workloads.


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