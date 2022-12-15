output "glue_data_bucket_name" {
  description = "The data bucket name"
  value       = aws_s3_bucket.aws_glue_mwaa_bucket.id
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