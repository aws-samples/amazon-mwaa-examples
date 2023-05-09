# Deploy ECS and RDS Resources using Terraform
This project gives instructions on how to setup the ECS and RDS resources 

## Deployment

### Prerequisites
- Terraform CLI
- AWS CLI

### Deploy the infrastructure
After running the `terraform apply`, be sure to replace the values with the values from your environment. 

```
$ terraform apply
var.assign_public_ip_to_task
  If using public subnets for MWAA environment, specify as true. Else, specify as false

  Enter a value: true

var.ecs_task_execution_role_arn
  The task execution role ARN. If making use of the same role being used for the existing MWAA environment, make sure it has permissions to access ECR and CloudWatch.

  Enter a value: arn:aws:iam::123456789:role/ecsTaskExecutionRole

var.elb_subnets
  A list of subnet_ids e.g. ["subnet-12345", "subnet-12345"]. Specify public subnets if creating a public facing load balancer and private subnets if creating an internal load balancer. 

  Enter a value: ["subnet-b06911ed", "subnet-f3bf01dd"]   

var.image_uri
  The mwaa-local-runner container image ECR URI that was built using the build script on your local.

  Enter a value:  123456789.dkr.ecr.us-east-1.amazonaws.com/mwaa-local-runner:latest

var.mwaa_subnet_ids
  A list of subnet_ids. Specify the subnets being used with the existing MWAA environment e.g. ["subnet-12345", "subnet-12345"]

  Enter a value: ["subnet-b06911ed", "subnet-f3bf01dd"]

var.region
  The region being deployed to.

  Enter a value: us-east-1

var.s3_dags_path
  The S3 path to the DAGs e.g. s3://my-airflow-bucket/dags

  Enter a value: s3://airflow-mwaa-test/DAG/

var.s3_plugins_path
  The S3 path to the plugins e.g. s3://my-airflow-bucket/plugins.zip

  Enter a value: s3://airflow-mwaa-test/plugins.zip

var.s3_requirements_path
  The S3 path to the requirements e.g. s3://my-airflow-bucket/requirements.txt

  Enter a value: s3://airflow-mwaa-test/requirements.txt

var.vpc_id
  The VPC ID. Specify the VPC ID being used with the MWAA environment.

  Enter a value: vpc-e4678d9f

var.vpc_security_group_ids
  A list of security groups. Specify the security group being used with the existing MWAA environment e.g. ["sg-12345"]

  Enter a value: ["sg-ad76c8e5"]
...
...
Do you want to perform these actions?
  Terraform will perform the actions described above.
  Only "yes" will be accepted to approve.

  Enter a value: yes
```

### Some things to take note of
#### S3 Bucket Policy
- Ensure that the S3 bucket that contains the DAGs, requirements and plugins allows the `ecs_task_execution_role_arn`.

#### Security group rules
- Ensure that the security group specified allows traffic all inbound and outbound traffic from the VPC CIDR range. This security group will be used for the ECS resources, the load balancer and the RDS database. 
- Ensure that the security group allows traffic from the IP of the machine that you will be accessing the Airflow UI from. If the security does not allow traffic from your machine, you will not be able to access the Airflow UI with a timeout error. 

### Clean up
To clean up the resources created, run the `terraform destroy` command and specify the values that were specified when creating the resources. 