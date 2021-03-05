### Amazon Managed Workflows for Apache Airflow (MWAA) and Amazon EMR

Use Amazon Managed Workflows for Apache Airflow (MWAA) to design and run a serverless workflow that coordinates Amazon Elastic Map Reduce (EMR) jobs. Amazon EMR is the industry-leading cloud big data platform for processing vast amounts of data using open source tools such as Apache Spark, Apache Hive, Apache HBase, Apache Flink, Apache Hudi, and Presto.

### Versions Supported

Apache Airflow 1.10.12 on Amazon MWAA

### Setup 

Copy the file into your DAGs folder, and ensure you have connectivity to Amazon EMR. For the latter, When using an AWS IAM role to connect to Amazon EMR, 
either with Amazon MWAA’s Execution Role or an assumed role in Amazon EC2, you will need to provide AmazonElasticMapReduceFullAccess Policy access to that 
role via the [AWS IAM console](https://console.aws.amazon.com/iam/home#/roles).  You will also need [Amazon EMR](https://aws.amazon.com/emr/getting-started/) 
configured on your AWS account.

### Files

* [1.10/emr_job.py](1.10/emr_job.py)
* [2.0/emr_job.py](2.0/emr_job.py)

### Requirements.txt needed

If using the 2.0 version on 1.10.12 use:
* [requirements/1.10/amazon_backport](../../requirements/1.10/amazon_backport)

### Plugins needed 

None.

### Explanation

All DAGs begin with the default import line:
```
from airflow import DAG
```
Then we will import the operators and sensors we will use in our workflow:
```
from airflow.contrib.operators.emr_add_steps_operator import EmrAddStepsOperator
from airflow.contrib.operators.emr_create_job_flow_operator import EmrCreateJobFlowOperator
from airflow.contrib.sensors.emr_step_sensor import EmrStepSensor
```
We’ll then import a couple of time utilities
```
from airflow.utils.dates import days_ago
from datetime import timedelta
```
Now we’ll define some default arguments to use in our tasks:
```
DEFAULT_ARGS = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email': ['airflow@example.com'],
    'email_on_failure': False,
    'email_on_retry': False,
}
```
Next we’ll define what our EMR cluster should look like.  This will use the mykeypair Key Pair, EMR_DefaultRole, and EMR_EC2_DefaultRole created above
```
JOB_FLOW_OVERRIDES = {
    'Name': 'my-demo-cluster',
    'ReleaseLabel': 'emr-5.30.1',
    'Applications': [
        {
            'Name': 'Spark'
        },
    ],    
    'Instances': {
        'InstanceGroups': [
            {
                'Name': "Master nodes",
                'Market': 'ON_DEMAND',
                'InstanceRole': 'MASTER',
                'InstanceType': 'm5.xlarge',
                'InstanceCount': 1,
            },
            {
                'Name': "Slave nodes",
                'Market': 'ON_DEMAND',
                'InstanceRole': 'CORE',
                'InstanceType': 'm5.xlarge',
                'InstanceCount': 2,
            }
        ],
        'KeepJobFlowAliveWhenNoSteps': False,
        'TerminationProtected': False,
        'Ec2KeyName': 'mykeypair',
    },
    'VisibleToAllUsers': True,
    'JobFlowRole': 'EMR_EC2_DefaultRole',
    'ServiceRole': 'EMR_DefaultRole'
}
```
We’ll also need to define the EMR job step we wish to run. In this case we’ll use the built-in calculate_pi sample
```
SPARK_STEPS = [
    {
        'Name': 'calculate_pi',
        'ActionOnFailure': 'CONTINUE',
        'HadoopJarStep': {
            'Jar': 'command-runner.jar',
            'Args': ['/usr/lib/spark/bin/run-example', 'SparkPi', '10'],
        },
    }
]
```
Next we’ll create our DAG object:
```
with DAG(
    dag_id='emr-job-dag',
    default_args=DEFAULT_ARGS,
    dagrun_timeout=timedelta(hours=2),
    start_date=days_ago(1),
    schedule_interval='@once',
    tags=['emr'],
) as dag:
```
We’ll define an EmrCreateJobFlowOperator that will create a new cluster
```
    cluster_creator = EmrCreateJobFlowOperator(
        task_id='create_job_flow', 
        emr_conn_id='aws_default', 
        job_flow_overrides=JOB_FLOW_OVERRIDES
    )

```
Then an EmrAddStepsOperator to add our calculate_pi step
```
    step_adder = EmrAddStepsOperator(
        task_id='add_steps',
        job_flow_id="{{ task_instance.xcom_pull(task_ids='create_job_flow', key='return_value') }}",
        aws_conn_id='aws_default',
        steps=SPARK_STEPS,
    )
```
And an EmrStepSensor that will wait for our step to complete
```
    step_checker = EmrStepSensor(
        task_id='watch_step',
        job_flow_id="{{ task_instance.xcom_pull('create_job_flow', key='return_value') }}",
        step_id="{{ task_instance.xcom_pull(task_ids='add_steps', key='return_value')[0] }}",
        aws_conn_id='aws_default',
    )
```
Finally we have to tell our DAG what order to run our operators
```
cluster_creator >> step_adder >> step_checker 
```
## Security

See [CONTRIBUTING](../../blob/main/CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../../blob/main/LICENSE) file.

