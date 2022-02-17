## Airflow sample migration scripts

This contains metadata migration scripts to migrate from one version of MWAA to another version of MWAA.
The sample contains only tables related to DAG history and audit. Some tables like Dag, DagTag, ab_permission, ab_role, ab_user etc are not needed to be migrated. 


## How to use

Follow the instructions in the [migration guide]()

- It be recommended to migratate a few dags at a time. You may want to add a where class in the export script to select the dags you are migrating to a new environment.

## Reference

- [Airflow database migration reference](https://github.com/apache/airflow/blob/0ebd6428e6b484790bfbbe1b8687ef4e6cae10e9/docs/apache-airflow/migrations-ref.rst)