module "rds-cluster" {
  source  = "cloudposse/rds-cluster/aws"
  version = "1.3.2"

  name                  = "database-mwaa-local-runner"

  cluster_identifier    = "database-mwaa-local-runner"
  cluster_family        = "aurora-postgresql13"
  admin_user            = "postgres"
  admin_password        = random_password.password.result
  engine                = "aurora-postgresql"
  engine_mode           = "provisioned"
  stage                 = "dev"

  subnets                       = var.mwaa_subnet_ids
  vpc_id                        = var.vpc_id
  vpc_security_group_ids        = var.vpc_security_group_ids

  serverlessv2_scaling_configuration = {
    min_capacity = 0.5
    max_capacity = 1
  }

  db_name               = "AirflowMetadata"
  cluster_size          = 1
}

resource "random_password" "password" {
  length           = 16
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}