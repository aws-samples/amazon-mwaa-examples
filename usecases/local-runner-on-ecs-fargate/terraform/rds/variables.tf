variable "vpc_id" {
    description = "The VPC ID. Specify the VPC ID being used with the MWAA environment."
    type = string
}

variable "mwaa_subnet_ids" {
    description = "A list of subnet_ids. Specify the subnets being used with the existing MWAA environment e.g. ['subnet-12345', 'subnet-12345']"
    type = list(string)
}

variable "vpc_security_group_ids" {
    description = "A list of security groups. This security group must allow itself in its rules. Specify the security group being used with the existing MWAA environment e.g. ['sg-12345']"
    type = list(string)
}