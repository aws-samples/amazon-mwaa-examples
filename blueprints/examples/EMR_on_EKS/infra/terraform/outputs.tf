output "configure_kubectl" {
  description = "Configure kubectl: make sure you're logged in with the correct AWS profile and run the following command to update your kubeconfig"
  value       = module.eks_blueprints.configure_kubectl
}

output "emrcontainers_virtual_cluster_id" {
  description = "EMR Containers Virtual cluster ID"
  value       = aws_emrcontainers_virtual_cluster.this.id
}

output "emr_on_eks_role_id" {
  description = "IAM execution role ID for EMR on EKS"
  value       = module.eks_blueprints.emr_on_eks_role_id
}

output "emr_on_eks_role_arn" {
  description = "IAM execution role arn for EMR on EKS"
  value       = module.eks_blueprints.emr_on_eks_role_arn
}

output "emr_on_eks_data_bucket" {
  description = "data bucket for EMR on EKS"
  value       = aws_s3_bucket.emr_eks_data_bucket.id
}
output "emr_on_eks_mwaa_iam_policy_arn" {
  description = "IAM policy for EMR EKS permission for MWAA"
  value       = aws_iam_policy.emr_on_eks_mwaa.arn
}

