### Amazon Managed Workflows for Apache Airflow (MWAA) Duplicate Role

Duplicates an existing RBAC role and assigns to a user

### Versions Supported

Apache Airflow 2.2.2 on Amazon MWAA, other 2.x versions and platforms may also work but are untested

### Setup 

Modify the DAG to reflect the NEW_ROLE, SOURCE_ROLE, and USER_NAME for your use case, copy the file into your DAGs folder, and run the dag once

### Files

* [2.2/duplicate_role.py](2.2/duplicate_role.py)

### Requirements.txt needed

None

### Plugins needed 

None.

## Security

See [CONTRIBUTING](../../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../blob/main/LICENSE) file.

