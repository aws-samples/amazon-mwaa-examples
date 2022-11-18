output "mwaa_webserver_url" {
  description = "The webserver URL of the MWAA Environment"
  value       = module.mwaa.mwaa_webserver_url
}

output "mwaa_arn" {
  description = "The ARN of the MWAA Environment"
  value       = module.mwaa.mwaa_arn
}


output "mwaa_role_arn" {
  description = "The ARN of the MWAA Environment"
  value       = module.mwaa.mwaa_role_arn
}

output "mwaa_role_name" {
  description = "The name of the MWAA Environment"
  value       = module.mwaa.mwaa_role_name
}

output "mwaa_security_group_id" {
  description = "The ARN of the MWAA Environment"
  value       = module.mwaa.mwaa_security_group_id
}

output "glue_data_bucket_name" {
  description = "The data bucket name"
  value       = aws_s3_bucket.aws_glue_mwaa_bucket.id
}

output "mwaa_bucket_name" {
  description = "The mwaa bucket name"
  value       = aws_s3_bucket.mwaa_bucket.id
}
output "glue_service_role_arn" {
  description = "Glue Service Role"
  value       = aws_iam_role.glue_service_role.arn
}
output "glue_service_role_name" {
  description = "Glue Service Role"
  value       = aws_iam_role.glue_service_role.name
}
output "glue_mwaa_iam_policy_arn" {
  description = "Glue Service Role"
  value       = aws_iam_policy.glue_mwaa_iam_policy.arn
}
