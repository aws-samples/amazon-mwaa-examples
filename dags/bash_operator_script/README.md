## Amazon Managed Workflows for Apache Airflow (MWAA) and bash operator
This script makes it easy to run a bash operator on the fly for troubleshooting purposes. 

### Versions Supported

Apache Airflow 1.10.12 on Amazon MWAA

### Prerequisites
- have a valid AWS CLI installation to use the MWAA CLI commands
- a linux or unix OS or similar interpreter with access to curl

### Setup 

- copy the bash_operator dag definition python file to the s3 bucket for MWAA
- verify that the dag is not paused in the airflow UI
- run the bash file, then watch the logs appear!
- once the logs are done using `ctrl + c` to break out of tailing the logs

#### Sample usage
`/bin/sh trigger_dag.sh --envname=test2 --dag=bash_command_conf_dag --command='echo $PATH'`

#### Sample output
```
Number of arguments: 3
args: --envname=test2 --dag=bash_command_conf_dag --command=echo $PATH
NAME = test2
DAG = bash_command_conf_dag
COMMAND = {"command":"echo $PATH"}
Output:
[2021-03-21 05:13:03,073] {{__init__.py:50}} INFO - Using executor CeleryExecutor
Created <DagRun bash_command_conf_dag @ 2021-03-21 05:13:03+00:00: manual__2021-03-21T05:13:03+00:00, externally triggered: True>
Errors:
2021-03-21T05:13:06 [2021-03-21 05:13:06,267] {{taskinstance.py:670}} INFO - Dependencies all met for <TaskInstance: bash_command_conf_dag.bash_command 2021-03-21T05:13:03+00:00 [queued]>
2021-03-21T05:13:06 [2021-03-21 05:13:06,413] {{taskinstance.py:670}} INFO - Dependencies all met for <TaskInstance: bash_command_conf_dag.bash_command 2021-03-21T05:13:03+00:00 [queued]>
2021-03-21T05:13:06 [2021-03-21 05:13:06,447] {{taskinstance.py:880}} INFO - 
--------------------------------------------------------------------------------
2021-03-21T05:13:06 [2021-03-21 05:13:06,478] {{taskinstance.py:881}} INFO - Starting attempt 1 of 1
2021-03-21T05:13:06 [2021-03-21 05:13:06,511] {{taskinstance.py:882}} INFO - 
--------------------------------------------------------------------------------
2021-03-21T05:13:06 [2021-03-21 05:13:06,564] {{taskinstance.py:901}} INFO - Executing <Task(BashOperator): bash_command> on 2021-03-21T05:13:03+00:00
2021-03-21T05:13:06 [2021-03-21 05:13:06,594] {{standard_task_runner.py:54}} INFO - Started process 1550 to run task
2021-03-21T05:13:06 [2021-03-21 05:13:06,594] {{standard_task_runner.py:54}} INFO - Started process 1550 to run task
2021-03-21T05:13:06 [2021-03-21 05:13:06,607] {{standard_task_runner.py:77}} INFO - Running: ['airflow', 'run', 'bash_command_conf_dag', 'bash_command', '2021-03-21T05:13:03+00:00', '--job_id', '126', '--pool', 'default_pool', '--raw', '-sd', 'DAGS_FOLDER/bash_operator_dag.py', '--cfg_path', '/tmp/tmphoc5rj_l']
2021-03-21T05:13:06 [2021-03-21 05:13:06,846] {{standard_task_runner.py:78}} INFO - Job 126: Subtask bash_command
2021-03-21T05:13:06 [2021-03-21 05:13:06,965] {{logging_mixin.py:112}} INFO - Running %s on host %s <TaskInstance: bash_command_conf_dag.bash_command 2021-03-21T05:13:03+00:00 [running]> ip-10-192-21-156.ec2.internal
2021-03-21T05:13:07 [2021-03-21 05:13:07,279] {{bash_operator.py:113}} INFO - Tmp dir root location: 
 /tmp
2021-03-21T05:13:07 [2021-03-21 05:13:07,309] {{bash_operator.py:136}} INFO - Temporary script location: /tmp/airflowtmp9tyf8zg1/bash_command4fzx9fgw
2021-03-21T05:13:07 [2021-03-21 05:13:07,341] {{bash_operator.py:146}} INFO - Running command: echo $PATH
2021-03-21T05:13:07 [2021-03-21 05:13:07,414] {{bash_operator.py:153}} INFO - Output:
2021-03-21T05:13:07 [2021-03-21 05:13:07,444] {{bash_operator.py:157}} INFO - /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
2021-03-21T05:13:07 [2021-03-21 05:13:07,485] {{bash_operator.py:161}} INFO - Command exited with return code 0
2021-03-21T05:13:07 [2021-03-21 05:13:07,525] {{taskinstance.py:1070}} INFO - Marking task as SUCCESS.dag_id=bash_command_conf_dag, task_id=bash_command, execution_date=20210321T051303, start_date=20210321T051306, end_date=20210321T051307
2021-03-21T05:13:11 [2021-03-21 05:13:11,224] {{logging_mixin.py:112}} INFO - [2021-03-21 05:13:11,224] {{local_task_job.py:102}} INFO - Task exited with return code 0
```

### Files

* [1.10/bash_operator.py](1.10/bash_operator.py)
* [1.10/trigger_dag.sh](1.10/trigger_dag.sh)

### Requirements.txt needed

None.

### Plugins needed 

None.

## Security

See [CONTRIBUTING](../../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../blob/main/LICENSE) file.

