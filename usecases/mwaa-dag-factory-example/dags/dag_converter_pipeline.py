from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.operators.python import PythonOperator
import os

def upload_yaml_to_s3(**context):
    """Upload converted YAML file to S3"""
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    
    s3_hook = S3Hook(aws_conn_id='aws_default')
    bucket_name = '{{S3_BUCKET_NAME}}'
    
    # Read the converted YAML file
    yaml_file_path = '/tmp/output_yaml/data_pipeline.yaml'
    
    if os.path.exists(yaml_file_path):
        with open(yaml_file_path, 'r') as f:
            yaml_content = f.read()
        
        # Upload to S3
        s3_hook.load_string(
            string_data=yaml_content,
            key='dags/converted/data_pipeline.yaml',
            bucket_name=bucket_name,
            replace=True
        )
        print(f"Successfully uploaded YAML to s3://{bucket_name}/dags/converted/data_pipeline.yaml")
    else:
        raise FileNotFoundError(f"YAML file not found at {yaml_file_path}")

with DAG(
    dag_id='dag_converter_pipeline',
    start_date=datetime(2025, 11, 1),
    schedule=None,  # Manual trigger (Airflow 3: schedule replaces schedule_interval)
    catchup=False,
    dagrun_timeout=timedelta(minutes=30),
    default_args={
        'owner': 'airflow',
        'retries': 1,
        'retry_delay': timedelta(minutes=2)
    },
    description='Install dag-converter and convert Python DAG to YAML'
) as dag:

    # Task 1: Install the wheel file
    install_wheel = BashOperator(
        task_id='install_dag_converter',
        bash_command="""
        set -e
        echo "Installing dag-converter from wheel file..."
        
        # Wheel file is already in /usr/local/airflow/dags/plugins/
        WHL_FILE="/usr/local/airflow/dags/plugins/python_to_yaml_dag_converter_mwaa_serverless-0.1.0-py3-none-any.whl"
        
        if [ ! -f "$WHL_FILE" ]; then
            echo "ERROR: Wheel file not found at $WHL_FILE"
            exit 1
        fi
        
        # Install the wheel
        pip install --user "$WHL_FILE"
        
        # Verify installation
        dag-converter --version || echo "dag-converter installed successfully"
        
        echo "Installation complete!"
        """
    )

    # Task 2: Convert Python DAG to YAML
    convert_dag = BashOperator(
        task_id='convert_python_to_yaml',
        bash_command="""
        set -e
        echo "Converting data_pipeline.py to YAML..."
        
        # Create output directory
        mkdir -p /tmp/output_yaml
        
        # DAG file is already synced to /usr/local/airflow/dags/
        DAG_FILE="/usr/local/airflow/dags/data_pipeline.py"
        
        if [ ! -f "$DAG_FILE" ]; then
            echo "ERROR: DAG file not found at $DAG_FILE"
            exit 1
        fi
        
        # Convert using dag-converter
        cd /usr/local/airflow/dags
        dag-converter convert data_pipeline.py --output /tmp/output_yaml
        
        # List the output
        echo "Conversion complete! Output files:"
        ls -la /tmp/output_yaml/
        
        # Show the content
        if [ -f /tmp/output_yaml/data_pipeline.yaml ]; then
            echo "=== Converted YAML Content ==="
            cat /tmp/output_yaml/data_pipeline.yaml
        fi
        """
    )

    # Task 3: Upload YAML to S3
    upload_yaml = PythonOperator(
        task_id='upload_yaml_to_s3',
        python_callable=upload_yaml_to_s3
        # Note: provide_context is deprecated in Airflow 3, context is always provided
    )

    # Set task dependencies
    install_wheel >> convert_dag >> upload_yaml
