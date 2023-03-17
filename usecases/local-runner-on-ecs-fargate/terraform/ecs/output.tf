output loadbalancer_url {
  value = aws_lb.loadbalancer.dns_name
}

output database_name {
    value = aws_rds_cluster.mwaa-local-runner-cluster.database_name
}

output rds_endpoint {
    value = aws_rds_cluster.mwaa-local-runner-cluster.endpoint
}

output db_passsword {
    value = aws_rds_cluster.mwaa-local-runner-cluster.master_password
    sensitive = true
}