output db_passsword {
  value     = random_password.password.result
  sensitive = true
}

output writer_instance_endpoint {
  value = module.rds-cluster.endpoint
}

output database_name {
  value = module.rds-cluster.database_name
}