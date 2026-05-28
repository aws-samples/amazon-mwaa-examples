## Disclaimer

AWS code samples are example code that demonstrates practical implementations of AWS services for specific use cases and scenarios.

These application solutions are not supported products in their own right, but educational examples to help our customers use our products for their applications. As our customer, any applications you integrate these examples into should be thoroughly tested, secured, and optimized according to your business's security standards & policies before deploying to production or handling production workloads.

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