# mwaa-custom-metrics

This is a sample implementation for the [blog](). By running the Makefile you can create a VPC with NAT/IGW, MWAA environment, associated IAM roles, CW dashboard etc

## Getting started

Visit the [blog]() for instructions

## To use the CW dashboard json
1. Replace $mwaa_env_name with your MWAA env name
2. Replace $region with your regions
3. Run ```aws cloudwatch put-dashboard --dashboard-name {dashboardname} --dashboard-body $(cat mwaa-cw-metric-dashboard.json)```

## Considerations
The listed metrics are just a few key metrics. Depending on your workload, you should be monitoring other metrics offerred in the AWS/MWAA namespace.
Airflow metrics are logged in MWAA custom namespace. You can learn more about the metrics from [here](https://docs.aws.amazon.com/mwaa/latest/userguide/access-metrics-cw-202.html)

