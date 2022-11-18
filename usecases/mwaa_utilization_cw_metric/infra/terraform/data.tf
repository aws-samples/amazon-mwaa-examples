data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}


data "aws_iam_policy_document" "aws_glue_mwaa_json" {
  statement {
    sid       = "GlueCommon"
    effect    = "Allow"
    resources = [ 
        "arn:${data.aws_partition.current.partition}:glue:${data.aws_region.current.id}:${local.account}:*"
    ]
    actions = [
                "glue:CreateJob",
                "glue:ListCrawlers",
                "glue:ListJobs",
                "glue:CreateCrawler"
    ]
  }
  statement {
    sid       = "GlueMetrics"
    effect    = "Allow"
    resources = [ 
        "*"
    ]
    actions = [
                "glue:GetCrawlerMetrics"
              ]
  }
  statement {
    sid       = "GlueCrawler"
    effect    = "Allow"
    resources = [ 
        "arn:${data.aws_partition.current.partition}:glue:${data.aws_region.current.id}:${local.account}:crawler/*"
    ]
    actions = [
                "glue:GetCrawler",
                "glue:StartCrawler",
                "glue:UpdateCrawler"
    ]
  }
  statement {
    sid       = "GlueJob"
    effect    = "Allow"
    resources = [ 
        "arn:${data.aws_partition.current.partition}:glue:${data.aws_region.current.id}:${local.account}:job/*"
    ]
    actions = [
                "glue:StartJobRun",
                "glue:GetJobRun",
                "glue:UpdateJob",
                "glue:GetJob"
    ]
  }

  statement {
    sid       = "Gluepassrole"
    effect    = "Allow"
    resources =  [aws_iam_role.glue_service_role.arn]
    actions = [
          "iam:PassRole",
          "iam:GetRole"
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
        "arn:${data.aws_partition.current.partition}:s3:::${aws_s3_bucket.aws_glue_mwaa_bucket.id}/*",
        "arn:${data.aws_partition.current.partition}:s3:::${aws_s3_bucket.aws_glue_mwaa_bucket.id}"
    ]
    actions = [
                "s3:PutObject*",
                "s3:ListBucket"
    ]
  }

}

