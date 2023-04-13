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

**Steps**
1. Open the `dynamic_task_mapping.py` file using a text editor of your choice. Change the value of **"YOUR_OWN_S3_BUCKET"** with the name of your own S3 Bucket. This has to be done in line 24 of teh DAG file.
2. Upload the files 1.txt, 2.txt and 3.txt that you would find the data directory to the S3 bucket under a folder prefix data. The final location of your files would be "YOUR_OWN_S3_BUCKET/data/1.txt", "YOUR_OWN_S3_BUCKET/data/2.txt" and "YOUR_OWN_S3_BUCKET/data/3.txt".
3. Ensure that your Amazon MWAA Airflow 2.4.3 env has access to read and write data in the S3 bucket.
4. Upload the `dynamic_task_mapping.py` file to the S3 bucket that is configured for your MWAA environment.
5. Enable the DAGs with id **"dynamic_task_mapping"** once they appear in the Airflow UI. 
6. Manually trigger the DAG with id **"dynamic_task_mapping"** from your Airflow UI.
7. Wait for it to complete execution. Review the Airflow logs. You would find the statement "Done. Returned value was: 40". This represents the sum of lines in the 3 files 1.txt, 2.txt and 3.txt.

### Files

dynamic_task_mapping.py
data/1.txt
data/2.txt
data/3.txt

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
