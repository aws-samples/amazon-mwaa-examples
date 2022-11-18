
#-----------------------------------------------------------
# Create an S3 buckets and upload DAG
#-----------------------------------------------------------

resource "aws_s3_bucket" "mwaa_bucket" {
  bucket_prefix = "mwaa-"
  tags   = var.tags
  force_destroy = true
}


resource "aws_s3_bucket_acl" "mwaa_bucket" {
  bucket = aws_s3_bucket.mwaa_bucket.id
  acl    = "private"
}

resource "aws_s3_bucket_versioning" "mwaa_bucket" {
  bucket = aws_s3_bucket.mwaa_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "mwaa_bucket" {
  bucket = aws_s3_bucket.mwaa_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "mwaa_bucket" {
  bucket                  = aws_s3_bucket.mwaa_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}


#-----------------------------------------------------------
# MWAA Airflow environment
#-----------------------------------------------------------
module "mwaa" {
  source = "aws-ia/mwaa/aws"

  name              = var.name
  airflow_version   = "2.2.2"
  environment_class = "mw1.small"
  create_s3_bucket  = false
  source_bucket_arn = aws_s3_bucket.mwaa_bucket.arn
  dag_s3_path       = "dags"
  
  
  logging_configuration = {
    dag_processing_logs = {
      enabled   = true
      log_level = "CRITICAL"
    }

    scheduler_logs = {
      enabled   = true
      log_level = "WARNING"
    }

    task_logs = {
      enabled   = true
      log_level = "INFO"
    }

    webserver_logs = {
      enabled   = true
      log_level = "CRITICAL"
    }

    worker_logs = {
      enabled   = true
      log_level = "WARNING"
    }
  }

  iam_role_additional_policies = [aws_iam_policy.glue_mwaa_iam_policy.arn,"arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSGlueServiceRole"
  ]
  min_workers        = 2
  max_workers        = 10
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnets

  webserver_access_mode = "PUBLIC_ONLY"   # Choose the Private network option(PRIVATE_ONLY) if your Apache Airflow UI is only accessed within a corporate network, and you do not require access to public repositories for web server requirements installation
  source_cidr           = ["10.1.0.0/16"] # Add your IP address to access Airflow UI

  tags = var.tags

}

#---------------------------------------------------------------
# VPC module
#---------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 3.0"

  name = var.name
  cidr = var.vpc_cidr

  azs             = local.azs
  public_subnets  = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k)]
  private_subnets = [for k, v in local.azs : cidrsubnet(var.vpc_cidr, 8, k + 10)]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true

  tags = var.tags
}


#-----------------------------------------------------------
# Create an S3 buckets for aws glue data
#-----------------------------------------------------------

resource "aws_s3_bucket" "aws_glue_mwaa_bucket" {
  bucket_prefix = "aws-glue-"
  tags   = var.tags
  force_destroy = true
}


resource "aws_s3_bucket_acl" "aws_glue_mwaa_bucket" {
  bucket = aws_s3_bucket.aws_glue_mwaa_bucket.id
  acl    = "private"
}

resource "aws_s3_bucket_versioning" "aws_glue_mwaa_bucket" {
  bucket = aws_s3_bucket.aws_glue_mwaa_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "aws_glue_mwaa_bucket" {
  bucket = aws_s3_bucket.aws_glue_mwaa_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "aws_glue_mwaa_bucket" {
  bucket                  = aws_s3_bucket.aws_glue_mwaa_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#---------------------------------------------------------------
# Glue Service Role
#---------------------------------------------------------------
resource "aws_iam_role" "glue_service_role" {
  name                = "DefaultAWSGlueServiceRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Sid    = ""
        Principal = {
          Service = "glue.amazonaws.com"
        }
      },
    ]
  })
  managed_policy_arns = [
    "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSGlueServiceRole"
    ]
}


#---------------------------------------------------------------
#  IAM Glue policies for attaching to Amazon MWAA environment
#---------------------------------------------------------------

resource "aws_iam_policy" "glue_mwaa_iam_policy" {
  name        = "glue-policies-mwaa"
  description = "IAM policy for Glue permissions for MWAA"
  path        = "/"
  policy      = data.aws_iam_policy_document.aws_glue_mwaa_json.json
}

#---------------------------------------------------------------
#   Amazon MWAA environment additional metrics dashboard
#---------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "mwaa_env_health_metric" {
  dashboard_name = "${var.name}_env_health_metric_dashboard"
  dashboard_body = jsonencode({
    widgets = local.widgets
  })
}

