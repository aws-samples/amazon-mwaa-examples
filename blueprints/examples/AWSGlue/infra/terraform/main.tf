


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

