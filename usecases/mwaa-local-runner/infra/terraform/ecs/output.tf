output loadbalancer_url {
  value = aws_lb.loadbalancer.dns_name
}

output database_name {
    value = module.rds_cluster.database_name
}

output rds_endpoint {
    value = module.rds_cluster.writer_instance_endpoint
}

output db_passsword {
    value = module.rds_cluster.db_passsword
    sensitive = true
}