## Interactive Commands with Amazon Managed Workflows for Apache Airflow (MWAA) and Bash Operator
This script serves as an example of how to run a bash operator in Amazon MWAA programmatically using the MWAA CLI API. This can be useful for debugging plugins or dependencies. 

### Versions Supported

Apache Airflow 1.10.12 on Amazon MWAA

### Prerequisites
- have a valid AWS CLI installation to use the MWAA CLI commands
- a linux or unix OS or similar interpreter with access to curl, awk, sleep, head, and jq

### Setup 

- copy the bash_operator dag definition python file to the s3 bucket for MWAA
- verify that the dag is not paused in the airflow UI
- run the bash file, then watch the logs appear!

### Explanation
#### trigger_dag.sh
The script will initially verify that the utilities aws, sleep, jq, head, and awk are available.
Then the aws version will be checked by running a list-environments MWAA API call.
A request will then be made to the airflow instance using curl to trigger the dag. This command is documented here
https://docs.aws.amazon.com/mwaa/latest/userguide/access-airflow-ui.html#create-cli-token-curl

```
STD_OUTPUT=""
STD_ERROR=""
CLI_JSON=$(aws mwaa create-cli-token --name $NAME --region $REGION) \
    && CLI_TOKEN=$(echo $CLI_JSON | jq -r '.CliToken') \
    && WEB_SERVER_HOSTNAME=$(echo $CLI_JSON | jq -r '.WebServerHostname') \
    && CLI_RESULTS=$(curl -s --request POST "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli" \
    --header "Authorization: Bearer $CLI_TOKEN" \
    --header "Content-Type: text/plain" \
    --data-raw "trigger_dag $DAG --conf '$COMMAND'") \
    && echo -n "Sent request to airflow using curl, Response body:" \
    && STD_OUTPUT=$(echo $CLI_RESULTS | jq -r '.stdout' | base64 --decode) \
    && echo $STD_OUTPUT \
    && echo -n "Errors:" \
    && STD_ERROR=$(echo $CLI_RESULTS | jq -r '.stderr' | base64 --decode) \
    && echo $STD_ERROR
```

The dag's status will then be queried using a similar curl command
```
CLI_JSON=$(aws mwaa create-cli-token --name $NAME)
CLI_TOKEN=$(echo $CLI_JSON | jq -r '.CliToken') \
    && WEB_SERVER_HOSTNAME=$(echo $CLI_JSON | jq -r '.WebServerHostname') \
    && CLI_RESULTS=$(curl -s "https://$WEB_SERVER_HOSTNAME/aws_mwaa/cli" \
    --header "Authorization: Bearer $CLI_TOKEN" \
    --header "Content-Type: application/json" \
    --data-raw "list_dag_runs --state running $DAG ") \
    && echo -n "Dag status: " \
    && STD_OUTPUT=$(echo $CLI_RESULTS | jq -r '.stdout' | base64 --decode) \
    && echo $STD_OUTPUT | awk -F"DAG RUNS" '{print $2}' | awk -F"|" '{print $8}' \
    && echo -n "Errors:" \
    && STD_ERROR=$(echo $CLI_RESULTS | jq -r '.stderr' | base64 --decode) \
    && echo $STD_ERROR
```
A full explanation of the above command [can be found here](https://tinyurl.com/2mj7zfxu)

The log stream is found using the following line which assumes the task name is **bash_command**

`LOG_STREAM_PREFIX=$DAG/bash_command/$(echo $STD_OUTPUT | head -n 1 | awk -F"[][]" '{print $2}' | awk -F"\ |," '{gsub(":","_",$2); print $1"T"$2}')`

The filter log groups command then queries and sorts the events based on timestamp in this line

`aws logs filter-log-events --log-group-name "airflow-$NAME-Task" --log-stream-name-prefix "$LOG_STREAM_PREFIX" --region $REGION --output text --query 'sort_by(events, &timestamp)[*].[message]'`

#### Sample usage

##### Echo path
`/bin/sh trigger_dag.sh --envname=test2 --dag=bash_operator --command='echo $PATH'`

##### Run a find command
`/bin/bash dags/bash_operator_script/1.10/trigger_dag.sh --envname=test2 --dag=bash_operator --command='find / -name \"pip\" 2>/dev/null' `

##### Run a pip freeze command
`/bin/bash dags/bash_operator_script/1.10/trigger_dag.sh --envname=test2 --dag=bash_operator --command='python /usr/lib/python3.7/site-packages/pip freeze'`

##### Run with a specific profile
`AWS_PROFILE=test /bin/bash dags/bash_operator_script/1.10/trigger_dag.sh --envname=test2 --dag=bash_operator --command='echo \"Hello world\"'`

##### Run a python command
`/bin/bash dags/bash_operator_script/1.10/trigger_dag.sh --envname=test2 --dag=bash_operator --command='python -c \"print(\\\"hello world\\\")\"'`

#### Sample output
```
Number of arguments: 3
args: --envname=test2 --dag=bash_operator --command=echo $PATH
NAME = test2
DAG = bash_operator
COMMAND = {"command":"echo $PATH"}
region = us-east-1
Sent request to airflow using curl, Response body:[2021-04-10 02:20:48,974] {{__init__.py:50}} INFO - Using executor CeleryExecutor Created <DagRun bash_operator @ 2021-04-10 02:20:48+00:00: manual__2021-04-10T02:20:48+00:00, externally triggered: True>
Errors:
waiting for run to finish...
Dag status:  running 
Errors:
waiting for 10 seconds...
Dag status: 
Errors:
dag has finished running, printing logs:
[2021-04-10 02:20:52,591] {{taskinstance.py:670}} INFO - Dependencies all met for <TaskInstance: bash_operator.bash_command 2021-04-10T02:20:48+00:00 [queued]>
[2021-04-10 02:20:52,804] {{taskinstance.py:670}} INFO - Dependencies all met for <TaskInstance: bash_operator.bash_command 2021-04-10T02:20:48+00:00 [queued]>
[2021-04-10 02:20:52,840] {{taskinstance.py:880}} INFO - 
--------------------------------------------------------------------------------
[2021-04-10 02:20:52,868] {{taskinstance.py:881}} INFO - Starting attempt 1 of 1
[2021-04-10 02:20:52,902] {{taskinstance.py:882}} INFO - 
--------------------------------------------------------------------------------
[2021-04-10 02:20:52,946] {{taskinstance.py:901}} INFO - Executing <Task(BashOperator): bash_command> on 2021-04-10T02:20:48+00:00
[2021-04-10 02:20:52,980] {{standard_task_runner.py:54}} INFO - Started process 460 to run task
[2021-04-10 02:20:52,980] {{standard_task_runner.py:54}} INFO - Started process 460 to run task
[2021-04-10 02:20:53,017] {{logging_mixin.py:112}} WARNING - Traceback (most recent call last):
[2021-04-10 02:20:53,104] {{logging_mixin.py:112}} WARNING -   File "/usr/local/airflow/config/cloudwatch_logging.py", line 106, in emit
    self.handler.emit(record)
[2021-04-10 02:20:53,132] {{logging_mixin.py:112}} WARNING -   File "/usr/local/lib/python3.7/site-packages/watchtower/__init__.py", line 217, in emit
    self._submit_batch([cwl_message], stream_name)
[2021-04-10 02:20:53,161] {{logging_mixin.py:112}} WARNING -   File "/usr/local/lib/python3.7/site-packages/watchtower/__init__.py", line 185, in _submit_batch
    self.sequence_tokens[stream_name] = response["nextSequenceToken"]
[2021-04-10 02:20:53,190] {{logging_mixin.py:112}} WARNING - KeyError: 'nextSequenceToken'
[2021-04-10 02:20:53,228] {{standard_task_runner.py:78}} INFO - Job 386: Subtask bash_command
[2021-04-10 02:20:53,391] {{logging_mixin.py:112}} INFO - Running %s on host %s <TaskInstance: bash_operator.bash_command 2021-04-10T02:20:48+00:00 [running]> ip-10-192-21-201.ec2.internal
[2021-04-10 02:20:53,575] {{bash_operator.py:113}} INFO - Tmp dir root location: 
 /tmp
[2021-04-10 02:20:53,607] {{bash_operator.py:136}} INFO - Temporary script location: /tmp/airflowtmpr8_o5_zr/bash_commandx9dwxbeh
[2021-04-10 02:20:53,639] {{bash_operator.py:146}} INFO - Running command: echo $PATH
[2021-04-10 02:20:53,691] {{bash_operator.py:153}} INFO - Output:
[2021-04-10 02:20:53,726] {{bash_operator.py:157}} INFO - /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/airflow/plugins/hadoop-3.3.0:/usr/local/airflow/plugins/apache-hive-3.1.2-bin/bin:/usr/local/airflow/plugins/apache-hive-3.1.2-bin/lib:/usr/local/airflow/plugins/hadoop-3.3.0:/usr/local/airflow/plugins/apache-hive-3.1.2-bin/bin:/usr/local/airflow/plugins/apache-hive-3.1.2-bin/lib:/usr/local/airflow/plugins/hadoop-3.3.0:/usr/local/airflow/plugins/apache-hive-3.1.2-bin/bin:/usr/local/airflow/plugins/apache-hive-3.1.2-bin/lib
[2021-04-10 02:20:53,759] {{bash_operator.py:161}} INFO - Command exited with return code 0
[2021-04-10 02:20:53,808] {{taskinstance.py:1070}} INFO - Marking task as SUCCESS.dag_id=bash_operator, task_id=bash_command, execution_date=20210410T022048, start_date=20210410T022052, end_date=20210410T022053
[2021-04-10 02:20:57,546] {{logging_mixin.py:112}} INFO - [2021-04-10 02:20:57,546] {{local_task_job.py:102}} INFO - Task exited with return code 0
```

### Files

* [1.10/bash_operator.py](1.10/bash_operator.py)
* [1.10/trigger_dag.sh](1.10/trigger_dag.sh)

### Requirements.txt needed

None.

### Plugins needed 

None.

### AWS APIs utilized
- [create-cli-token](https://docs.aws.amazon.com/mwaa/latest/userguide/mwaa-actions-resources.html)
- [list-environments](https://docs.aws.amazon.com/mwaa/latest/userguide/mwaa-actions-resources.html)
- [filter-log-events](https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_FilterLogEvents.html)

### Airflow APIs utilized
- [trigger_dag](http://airflow.apache.org/docs/apache-airflow/1.10.12/cli-ref.html#trigger_dag)
- [list_dag_runs](http://airflow.apache.org/docs/apache-airflow/1.10.12/cli-ref.html#list_dag_runs)

All MWAA supported airflow CLI commands are listed here:

https://docs.aws.amazon.com/mwaa/latest/userguide/access-airflow-ui.html#airflow-cli-commands-supported

## Security

See [CONTRIBUTING](../../CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../LICENSE) file.

