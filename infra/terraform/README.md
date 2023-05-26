
# Welcome to your MWAA Terrafom project!

Welcome to Amazon MWAA Blueprints !

This repository contains a collection of code that aim to make it easier and faster for customers to adopt Amazon MWAA. It can be used by AWS customers, partners, and internal AWS teams to configure and manage complete MWAA environment that are fully bootstrapped with the operational software that is needed to deploy and operate workloads.



## Getting Started

### Prerequisites

First, ensure that you have installed the following tools locally.

1. [aws cli](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
2. [terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli)
3. [MWAA deployer Permissions](https://docs.aws.amazon.com/mwaa/latest/userguide/access-policies.html#full-access-policy)

### Deployment Steps
Initialize the working directory with the following:

```sh
terraform init
```

### Terraform PLAN

Verify the resources that will be created by this execution:

```sh
terraform plan
```

### Terraform APPLY

```sh
terraform apply
```
We will leverage Terraform's [target](https://learn.hashicorp.com/tutorials/terraform/resource-targeting?in=terraform/cli) functionality to deploy a VPC, an MWAA environment and IAM role.

### Validate
The above step will take atleast 25 mins to complete the creation of MWAA environment.
Run the command in your terminal.

```sh
aws aws mwaa list-environments
```
You should see output similar to below
```
{
    "Environments": [
        "MWAA-Environment"
    ]
}
```

### Cleanup
```sh
terraform destroy
```
