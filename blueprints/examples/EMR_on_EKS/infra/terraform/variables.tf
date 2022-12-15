variable "eks_cluster_id" {
  description = "EKS Cluster ID"
  type        = string
  default = "emr_eks_cluster"
}

variable "cluster_version" {
  description = "EKS cluster version"
  type        = string
  default = "1.23"
}

variable "name" {
  description = "name"
  type        = string
  default = "emr_eks_blueprint"
}

variable "data_bucket_name" {
  description = "S3 data bucket for EMR on EKS"
  type        = string
  default = null
}
variable "tags" {
  description = "Common Tags for AWS resources"
  type        = map(string)
  default     = {}
}

variable "vpc_id" {
  description = "VPC of the EKS cluster"
  type        = string
}

variable "private_subnet_ids" {
  description = <<-EOD
  (Required) The private subnet IDs in which EKS cluster should be created - format ["a","b"].
  EOD
  type        = list(string)
}

variable "instance_types" {
  description = "managed node instance type "
  type        = list
  default = ["m5.large"]
}

variable "iam_role_path" {
  description = "IAM role path"
  type        = string
  default     = "/"
}

variable "iam_role_permissions_boundary" {
  description = "ARN of the policy that is used to set the permissions boundary for the IAM role"
  type        = string
  default     = null
}
