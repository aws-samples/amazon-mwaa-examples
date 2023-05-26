output "mwaa_webserver_url" {
  description = "The webserver URL of the MWAA Environment"
  value       = module.mwaa.mwaa_webserver_url
}

output "mwaa_arn" {
  description = "The ARN of the MWAA Environment"
  value       = module.mwaa.mwaa_arn
}

output "mwaa_service_role_arn" {
  description = "The Service Role ARN of the Amazon MWAA Environment"
  value       = module.mwaa.mwaa_service_role_arn
}

output "mwaa_status" {
  description = "The status of the Amazon MWAA Environment"
  value       = module.mwaa.mwaa_status
}

output "mwaa_role_arn" {
  description = "IAM Role ARN of the MWAA Environment"
  value       = module.mwaa.mwaa_role_arn
}

output "aws_s3_bucket_name" {
  description = "S3 bucket Name of the MWAA Environment"
  value       = module.mwaa.aws_s3_bucket_name
  }

output "vpc_id" {
  description = "MWAA VPC ID"
  value       = module.vpc.vpc_id
}
output "subnets" {
  description = "MWAA VPC private_subnets"
  value       = module.vpc.private_subnets
}
