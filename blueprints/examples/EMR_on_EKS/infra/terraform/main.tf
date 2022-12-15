

provider "kubernetes" {
  host                   = module.eks_blueprints.eks_cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks_blueprints.eks_cluster_certificate_authority_data)
  token                  = data.aws_eks_cluster_auth.this.token
}
data "aws_eks_cluster_auth" "this" {
  name = module.eks_blueprints.eks_cluster_id
}

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

locals {
  name   = var.name
  vpc_id = var.vpc_id
  tags = merge(var.tags, {
    Blueprint  = local.name
    GithubRepo = "github.com/aws-ia/terraform-aws-eks-blueprints"
  })
}

module "eks_blueprints" {
  source = "github.com/aws-ia/terraform-aws-eks-blueprints?ref=v4.12.0"

  # EKS CLUSTER
  cluster_version           = var.cluster_version
  vpc_id                    = local.vpc_id                                   
  private_subnet_ids        = var.private_subnet_ids      
  cluster_name              = var.eks_cluster_id
  # EKS MANAGED NODE GROUPS
  managed_node_groups = {
    mg_m5 = {
      node_group_name = "managed-ondemand"
      instance_types  = var.instance_types
      subnet_ids      = var.private_subnet_ids
    }
  }
  enable_emr_on_eks = true
  emr_on_eks_teams = {
    emr-data-team-a = {
      namespace               = "emr-data-team-a"
      job_execution_role      = "emr-eks-data-team-a"
      additional_iam_policies = [aws_iam_policy.emr_on_eks.arn]
    }
    emr-data-team-b = {
      namespace               = "emr-data-team-b"
      job_execution_role      = "emr-eks-data-team-b"
      additional_iam_policies = [aws_iam_policy.emr_on_eks.arn]
    }
  }
  tags = local.tags

}
#---------------------------------------------------------------
# Example IAM policies for EMR job execution
#---------------------------------------------------------------
data "aws_iam_policy_document" "emr_on_eks" {
  statement {
    sid       = ""
    effect    = "Allow"
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${aws_s3_bucket.emr_eks_data_bucket.id}",
      "arn:${data.aws_partition.current.partition}:s3:::${aws_s3_bucket.emr_eks_data_bucket.id}/*"
    ]

    actions = [
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:PutObject",
    ]
  }

  statement {
    sid       = ""
    effect    = "Allow"
    resources = ["arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:log-group:*"]

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents",
    ]
  }
}

resource "aws_iam_policy" "emr_on_eks" {
  name        = format("%s-%s", local.name, "emr-job-iam-policies")
  description = "IAM policy for EMR on EKS Job execution"
  path        = "/"
  policy      = data.aws_iam_policy_document.emr_on_eks.json
}

#---------------------------------------------------------------
# Create EMR on EKS Virtual Cluster
#---------------------------------------------------------------
resource "aws_emrcontainers_virtual_cluster" "this" {
  name = format("%s-%s", module.eks_blueprints.eks_cluster_id, "emr-data-team-a")

  container_provider {
    id   = module.eks_blueprints.eks_cluster_id
    type = "EKS"

    info {
      eks_info {
        namespace = "emr-data-team-a"
      }
    }
  }
}


#---------------------------------------------------------------
# Example IAM policies for attaching to Amazon MWAA environment
#---------------------------------------------------------------
data "aws_iam_policy_document" "emr_on_eks_mwaa" {
  statement {

    sid       = "emrcontainers"
    effect    = "Allow"
    resources = [ 
        "arn:${data.aws_partition.current.partition}:emr-containers:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:/*",
        "arn:${data.aws_partition.current.partition}:emr-containers:${data.aws_region.current.id}:${data.aws_caller_identity.current.account_id}:/virtualclusters/*/jobruns/*"
    ]

    actions = [
          "emr-containers:ListVirtualClusters",
          "emr-containers:CreateVirtualCluster",
          "emr-containers:StartJobRun",
          "emr-containers:DescribeJobRun",
          "emr-containers:ListJobRuns",
          "emr-containers:CancelJobRun",
          "emr-containers:DeleteVirtualCluster",
    ]

  }

  statement {

    sid       = "emrcontainerspassrole"
    effect    = "Allow"
    resources =  "${module.eks_blueprints.emr_on_eks_role_arn}"
    actions = [
          "iam:PassRole",
    ]

  }

  ## This statement is needed for copying weather station data ###
  statement {

    sid       = "s3Remote"
    effect    = "Allow"
    resources = [ 
        "arn:${data.aws_partition.current.partition}:s3:::noaa-ghcn-pds/*",
        "arn:${data.aws_partition.current.partition}:s3:::noaa-ghcn-pds"
    ]

    actions = [
                "s3:GetObject",
                "s3:ListBucket"
    ]

  }
  statement {

    sid       = "s3Local"
    effect    = "Allow"
    resources = [ 
        "arn:${data.aws_partition.current.partition}:s3:::${aws_s3_bucket.emr_eks_data_bucket.id}/*",
        "arn:${data.aws_partition.current.partition}:s3:::${aws_s3_bucket.emr_eks_data_bucket.id}"
    ]

    actions = [
                "s3:PutObject*",
                "s3:ListBucket"
    ]

  }



}

resource "aws_iam_policy" "emr_on_eks_mwaa" {
  name        = format("%s-%s", local.name, "emr-job-iam-policies-mwaa")
  description = "IAM policy for EMR on EKS Job permissions for MWAA"
  path        = "/"
  policy      = data.aws_iam_policy_document.emr_on_eks_mwaa.json
}

# ---------------------------------------------------------------------------------------------------------------------
# EMR EKS S3 data Bucket
# ---------------------------------------------------------------------------------------------------------------------
#tfsec:ignore:AWS017 tfsec:ignore:AWS002 tfsec:ignore:AWS077
resource "aws_s3_bucket" "emr_eks_data_bucket" {

  bucket_prefix = var.data_bucket_name != null ? var.data_bucket_name : format("%s-%s-", "emr-eks", data.aws_caller_identity.current.account_id)
  tags          = var.tags
}

resource "aws_s3_bucket_acl" "emr_eks_data_bucket" {

  bucket = aws_s3_bucket.emr_eks_data_bucket.id
  acl    = "private"
}

#tfsec:ignore:aws-s3-encryption-customer-key
resource "aws_s3_bucket_server_side_encryption_configuration" "mwaa" {
 
  bucket = aws_s3_bucket.emr_eks_data_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "emr_eks_data_bucket" {

  bucket = aws_s3_bucket.emr_eks_data_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  restrict_public_buckets = true
  ignore_public_acls      = true
}

