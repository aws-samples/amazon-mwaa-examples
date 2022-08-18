### Amazon Managed Workflows for Apache Airflow (MWAA) Get DAG ID

If the dag parse is in the context of a DAG execution, this function will return the DAG ID.  

This work is based on the article
https://medium.com/apache-airflow/magic-loop-in-airflow-reloaded-3e1bd8fb6671

### Versions Supported

Apache Airflow 2.2.2, tested on Amazon MWAA.  Other 2.x versions and platforms may also work but are untested.

### Setup 

This function, when referenced from an Airflow DAG, will return NULL if not part of a 
Celery Task execution, or will return the DAG ID string if it is.

The file `get_dag_id_example.py` creates N dags, one per table row, but will only retrieve SQL statement for 
particular table row if it is being called from a task, otherwise it skips that retrieval.  Simlarly, it
only creates the DAG itself if it is part of the Scheduler processing loop (`current_dag = None`) or
if the DAG has the same ID as the one currently being processed.

### Files

* [2.2/get_dag_id.py](2.2/get_dag_id.py)
* [2.2/get_dag_id_example.py](2.2/get_dag_id_example.py)

### Requirements.txt needed

None

### Plugins needed 

None.

## Security

See [CONTRIBUTING](../../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../blob/main/LICENSE) file.
