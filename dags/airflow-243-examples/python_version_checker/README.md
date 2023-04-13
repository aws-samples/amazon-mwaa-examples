## Amazon Managed Workflows for Apache Airflow (MWAA) CloudFormation Templates

Example CloudFormation templates for Amazon MWAA.  See [AWS CloudFormation documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-mwaa-environment.html) for details.

### Versions Supported
Apache Airflow 2.4.3 on Amazon MWAA.

### Setup 
**Pre-Requisites**
- An Amazon MWAA environment configured with Apache Airflow v2.4.3. 
**Steps**
1. Upload the `python-version.py` file to S3 Bucket that is configured for your MWAA environment.
2. Enable the DAGs with id **"python_version_checker"** once they appear in the Airflow UI. 
6. Manually trigger the DAG with id **"python_version_checker"** from your Airflow UI.
7. Wait for it to complete execution. Review the Airflow logs. You would find the statement "Python 3.10.8". This represents the installed Python version on your Amazon MWAA environment.

### Files
python-version.py

### Requirements.txt needed
None

### Plugins needed 
None

### Explanation
For easier readability, the respective DAG file code has inline comments to help with explanation.

## Security

See [CONTRIBUTING](../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../blob/main/LICENSE) file.
