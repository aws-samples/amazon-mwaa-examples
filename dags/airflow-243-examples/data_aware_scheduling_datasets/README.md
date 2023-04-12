## Amazon Managed Workflows for Apache Airflow (MWAA) CloudFormation Templates

Example CloudFormation templates for Amazon MWAA.  See [AWS CloudFormation documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-mwaa-environment.html) for details.

### Versions Supported
Apache Airflow 2.4.3 on Amazon MWAA.

### Setup 
**Pre-Requisites**
- An Amazon Simple Storage Service (Amazon S3) bucket to upload datasets in.
This can be a separate prefix in your existing Amazon S3 bucket configured for
your MWAA env or it can be a completely different Amazon S3 bucket that you
identify to store your data in.
- An Amazon MWAA environment configured with Apache Airflow v2.4.3. The
MWAA execution role should have access to read and write to the Amazon S3
bucket configured to upload datasets. The latter is only needed if it is a different
bucket than the MWAA bucket.

1. Open the producer.py file using a text editor of your choice. Change the value of "YOUR_OWN_S3_BUCKET" with the name of your own S3 Bucket. This has to be done in two places: line 24 and line 26.
2. Open the consumer.py file using a text editor of your choice. Change the value of "YOUR_OWN_S3_BUCKET" with the name of your own S3 Bucket. This has to be done in two places: line 22 and line 24.
3. Ensure that your Amazon MWAA Airflow 2.4.3 env has access to read and write data in the S3 bucket.
4. Upload both the producer.py and consumer.py files to the S3 bucket that is configured for your MWAA environment.
5. Manually trigger the DAG with id "data_aware_producer" from your Airflow UI
6. Wait for it to complete execution. You would notice that after it finishes, the DAG "data_aware_consumer" has automatically been triggered.

### Files

1. producer.py
2. consumer.py

### Requirements.txt needed
None

### Plugins needed 
None

### Explanation

## Security

See [CONTRIBUTING](../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../blob/main/LICENSE) file.
