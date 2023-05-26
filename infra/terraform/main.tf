# ---------------------------------------------------------------------------------------------------------------------
# MWAA Environment
# ---------------------------------------------------------------------------------------------------------------------

module "mwaa" {
  source = "aws-ia/mwaa/aws"

  name                 = var.name
  airflow_version      = var.mwaa_version
  environment_class    = "mw1.medium"

  vpc_id                = "${module.vpc.vpc_id}"
  private_subnet_ids    = slice("${module.vpc.private_subnets}",0,2)

  min_workers           = 1
  max_workers           = 10
  webserver_access_mode = "PUBLIC_ONLY" # Default PRIVATE_ONLY for production environments

  logging_configuration = {
    dag_processing_logs = {
      enabled   = true
      log_level = "INFO"
    }

    scheduler_logs = {
      enabled   = true
      log_level = "INFO"
    }

    task_logs = {
      enabled   = true
      log_level = "INFO"
    }

    webserver_logs = {
      enabled   = true
      log_level = "INFO"
    }

    worker_logs = {
      enabled   = true
      log_level = "INFO"
    }
  }

  airflow_configuration_options = {
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals  {
  azs = slice(data.aws_availability_zones.available.names,0,3)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"

  name = var.name
  cidr = var.vpc_cidr

  azs             = local.azs
  public_subnets  = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k)]
  private_subnets = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k + 10)]

  enable_nat_gateway   = true
  #single_nat_gateway   = true
  enable_dns_hostnames = true

  # Manage so we can name
  manage_default_network_acl    = true
  default_network_acl_tags      = { Name = "${var.name}-default" }
  manage_default_route_table    = true
  default_route_table_tags      = { Name = "${var.name}-default" }
  manage_default_security_group = true
  default_security_group_tags   = { Name = "${var.name}-default" }

  default_security_group_name = "${var.name}-endpoint-secgrp"

  default_security_group_ingress = [
    {
      protocol    = -1
      from_port   = 0
      to_port     = 0
      cidr_blocks = var.vpc_cidr
  }]
  default_security_group_egress = [
    {
      from_port   = 0
      to_port     = 0
      protocol    = -1
      cidr_blocks = "0.0.0.0/0"
  }]

  tags = var.tags
}
