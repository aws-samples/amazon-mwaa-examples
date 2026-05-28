## Disclaimer

AWS code samples are example code that demonstrates practical implementations of AWS services for specific use cases and scenarios.

These application solutions are not supported products in their own right, but educational examples to help our customers use our products for their applications. As our customer, any applications you integrate these examples into should be thoroughly tested, secured, and optimized according to your business's security standards & policies before deploying to production or handling production workloads.

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