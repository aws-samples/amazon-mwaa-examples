### Amazon Managed Workflows for Apache Airflow (MWAA) GCP Backport Providers

Use Amazon Managed Workflows for Apache Airflow (MWAA) with Apache Airflow GCP backport providers.

### Versions Supported

Apache Airflow 1.10.12 on Amazon MWAA

### Setup 

Copy the file into your MWAA S3 bucket and update your environment to use this version.  May be combined with other requirements.  
See [Amazon MWAA documentation](https://docs.aws.amazon.com/mwaa/latest/userguide/working-dags-dependencies.html) for more details.

### Files

* [1.10/requirements_gcp_backport.txt](1.10/requirements_gcp_backport.txt)

### Explanation

This file specifies specific versions that are known to work on Apache Airflow 1.10.12 on Amazon Linux.  For more details on backport providers 
see [Apache Airflow Backport Providers](https://airflow.apache.org/docs/apache-airflow/stable/backport-providers.html) for details.
```
grpcio==1.27.2
cython==0.29.21
pandas-gbq==0.13.3
cryptography==3.3.2
apache-airflow-backport-providers-amazon[google]
```
## Security

See [CONTRIBUTING](../../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../blob/main/LICENSE) file.

