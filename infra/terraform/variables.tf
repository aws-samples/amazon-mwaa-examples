variable "vpc_cidr" {
  description = "(Required) The name of the Apache Airflow MWAA Environment"
  type        = string
  default     = "10.1.0.0/16"

}

variable "tags" {
  description = "(Optional) A map of resource tags to associate with the resource"
  type        = map(string)
  default     = {}
}

variable "name" {
  description = "(Required) The name of the Apache Airflow MWAA Environment"
  type        = string
  default = "MWAA_Environment"
}
variable "mwaa_version" {
  description = "(Required) The name of the Apache Airflow MWAA Environment"
  type        = string
  default = "2.5.1"
}