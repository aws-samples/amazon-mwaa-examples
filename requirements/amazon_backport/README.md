## Disclaimer

AWS code samples are example code that demonstrates practical implementations of AWS services for specific use cases and scenarios.

These application solutions are not supported products in their own right, but educational examples to help our customers use our products for their applications. As our customer, any applications you integrate these examples into should be thoroughly tested, secured, and optimized according to your business's security standards & policies before deploying to production or handling production workloads.

### Amazon Managed Workflows for Apache Airflow (MWAA) and Backport Providers

Use Amazon Managed Workflows for Apache Airflow (MWAA) with Apache Airflow Amazon backport providers.

### Versions Supported

Apache Airflow 1.10.12 on Amazon MWAA

### Setup 

Copy the file into your MWAA S3 bucket and update your environment to use this version.  May be combined with other requirements.  
See [Amazon MWAA documentation](https://docs.aws.amazon.com/mwaa/latest/userguide/working-dags-dependencies.html) for more details.

### Files

* [1.10/requirements_amazon_backport.txt](1.10/requirements_amazon_backport.txt)

### Explanation

Just one line.  See [Apache Airflow Backport Providers](https://airflow.apache.org/docs/apache-airflow/stable/backport-providers.html) for details.
```
apache-airflow-backport-providers-amazon
```
## Security

See [CONTRIBUTING](../../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../blob/main/LICENSE) file.