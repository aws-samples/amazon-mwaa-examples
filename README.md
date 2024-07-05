## Amazon Managed Workflows for Apache Airflow (MWAA) Examples

This repository contains example DAGs, requirements.txt, plugins, and CloudFormation templates focused on Amazon MWAA.  Since Amazon MWAA is running open-source Apache Airflow many of the contributions will be applicable for self-managed implementations as well.

### Contributing

We want examples of as many use cases in this repository as possible! Please submit a Pull Request if you would like to add something.

### DAG Files

Example Directed Acyclic Graph (DAG) workflows that have been tested to work on Amazon MWAA.  Associated requirements.txt will be referenced to the entry in the next section. See [Amazon MWAA documentation](https://docs.aws.amazon.com/mwaa/latest/userguide/configuring-dag-folder.html) for details. 

* [Move your Apache Airflow Connections and Variables to AWS Secrets Manager](dags/metadb_to_secrets_manager)
* [Amazon Managed Workflows for Apache Airflow (MWAA) and Amazon EMR](dags/emr_job)
* [Interactive Commands with Amazon MWAA and Bash Operator](dags/bash_operator_script)
* [Duplicate an existing RBAC role and assign to a user](dags/duplicate_role)
* [Return DAG ID when parsed during task execution](dags/get_dag_id)

### Use Cases
This [folder](./usecases) contains complete set of sample use cases including documentation, infrastructure as code, and dependant resources. Follow the README.md in each use case to get started.

* [Image Processing Pipeline](usecases/image-processing)
* [Amazon MWAA with AWS CodeArtifact for Python dependencies](usecases/mwaa-with-codeartifact)
* [Stop and Start MWAA](usecases/start-stop-mwaa-environment/)

### Requirements.txt

Sometimes getting the right combination of Python libraries is tricky. This repository is here to help. See [Amazon MWAA documentation](https://docs.aws.amazon.com/mwaa/latest/userguide/working-dags-dependencies.html) for details. 

* [Amazon Backport Providers](requirements/amazon_backport)
* [GCP Backport Providers](requirements/gcp_backport)

### Plugins

Most Airflow community plugins will work fine on Amazon MWAA.  This repository is for specific examples that have been testing on the service. See [Amazon MWAA documentation](https://docs.aws.amazon.com/mwaa/latest/userguide/configuring-dag-import-plugins.html) for details. 

### CloudFormation

Example CloudFormation templates for Amazon MWAA.  See [AWS CloudFormation documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-mwaa-environment.html) for details.

* 

### IAM Policies

Example AWS IAM Policy definitions.  See [Amazon MWAA documentation](https://docs.aws.amazon.com/mwaa/latest/userguide/manage-access.html) for details. 

* 

### Setup for the examples

These examples all assume a working [Amazon MWAA environment](https://aws.amazon.com/managed-workflows-for-apache-airflow/).

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

