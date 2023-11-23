## Amazon MWAA with AWS Glue and Amazon Athena

### Overview

This solution demonstrates different ways to orchestrate Glue jobs and Athena queries from Amazon MWAA

### Instructions

Note: Please run this tutorial in an account and region where AWS Lake Formation is not enabled. 

1. Create resources by utilising cloud formation template with name "RDSMWAA.yaml". Add a CFN name when prompted and leave rest of the settings as default. Wait for CFN to complete.

2. Get the artifact bucket name from cloud formation (CFN) output (check for "artifactBucket" key in CFN output). Copy the "ArtifactBucket" folder contents to the corresponding S3 bucket. You can select all of the sub-folders and then drag and drop.

3. Get the MWAA environment bucket name from CFN output (check for "MWAAEnvironmentBucket" key in CFN output). Copy the "MWAAEnvironmentBucket" folder contents to the corresponding S3 bucket. You can select all of the sub-folders and then drag and drop.

4. From the Airflow user interface: The "create resources" dag should run automatically to create the database. Before running any Athena DAGs, be sure to trigger data-pipeline dag that ingests data from RDS and puts into S3. Trigger run-athena dag to execute Athena queries.

### Clean up

1. Empty content from both s3 bucket - mwaaenvironment  and artifact
   
2. Delete CloudFormation stack


### Resources

- Amazon MWAA docs https://docs.aws.amazon.com/mwaa 
- #airflow-aws Slack Channel: https://apache-airflow.slack.com 
- MWAA workshop: https://amazon-mwaa-for-analytics.workshop.aws/en/
- MWAA local development and testing: https://github.com/aws/aws-mwaa-local-runner
- Glue Docs: https://docs.aws.amazon.com/glue/latest/dg/how-it-works.html 
- Athena Docs: https://docs.aws.amazon.com/athena/latest/ug/what-is.html 
- MWAA at Scale: https://s12d.com/MWAAatScale 
- Airflow at Scale: https://s12d.com/AirflowAtScale 
