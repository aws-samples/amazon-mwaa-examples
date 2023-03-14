variable "vpc_id" {
    description = "The VPC ID. Specify the VPC ID being used with the MWAA environment."
    type = string
}

variable "mwaa_subnet_ids" {
    description = "A list of subnet_ids. Specify the subnets being used with the existing MWAA environment e.g. ['subnet-12345', 'subnet-12345']"
    type = list(string)
}

variable "elb_subnets" {
    description = "A list of subnet_ids. Specify public subnets if creating a public facing load balancer and private subnets if creating an internal load balancer."
    type = list(string)
}

variable "vpc_security_group_ids" {
    description = "A list of security groups. Specify the security group being used with the existing MWAA environment e.g. ['sg-12345']"
    type = list(string)
}

variable "image_uri" {
    description = "The mwaa-local-runner container image ECR URI that was built using the build script on your local."
    type = string
}

variable "ecs_task_execution_role_arn" {
    description = "The task execution role ARN. If making use of the same role being used for the existing MWAA environment, make sure it has permissions to access ECR and CloudWatch."
    type = string
}

variable "s3_dags_path" {
    description = "The S3 path to the DAGs e.g. s3://my-airflow-bucket/dags"
    type = string
}

variable "s3_plugins_path" {
    description = "The S3 path to the plugins e.g. s3://my-airflow-bucket/plugins.zip"
    type = string
}

variable "s3_requirements_path" {
    description = "The S3 path to the requirements e.g. s3://my-airflow-bucket/requirements.txt"
    type = string
}

variable "assign_public_ip_to_task" {
    description = "If using public subnets for MWAA environment, specify as true. Else, specify as false"
    type = bool
}

variable "region" {
    description = "The region being deployed to."
    type = string
}