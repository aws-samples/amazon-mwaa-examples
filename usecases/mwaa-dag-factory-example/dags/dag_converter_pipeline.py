from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.operators.python import PythonOperator
import os

def upload_yaml_to_s3(**context):
    """Upload converted YAML file to S3"""
    from airflow.providers.amazon.aws.hooks.s3 import S3Hook
    import glob
    
    s3_hook = S3Hook(aws_conn_id='aws_default')
    bucket_name = '{{S3_BUCKET_NAME}}'
    
    # Find all YAML files in the output directory
    output_dir = '/tmp/output_yaml'
    yaml_files = glob.glob(f'{output_dir}/*.yaml') + glob.glob(f'{output_dir}/*.yml')
    
    if not yaml_files:
        raise FileNotFoundError(f"No YAML files found in {output_dir}")
    
    print(f"Found {len(yaml_files)} YAML file(s) to upload:")
    for yaml_file in yaml_files:
        print(f"  - {yaml_file}")
    
    # Upload each YAML file
    uploaded_count = 0
    for yaml_file_path in yaml_files:
        try:
            with open(yaml_file_path, 'r') as f:
                yaml_content = f.read()
            
            # Get the filename
            filename = os.path.basename(yaml_file_path)
            s3_key = f'dags/converted/{filename}'
            
            # Upload to S3
            s3_hook.load_string(
                string_data=yaml_content,
                key=s3_key,
                bucket_name=bucket_name,
                replace=True
            )
            print(f"✓ Successfully uploaded {filename} to s3://{bucket_name}/{s3_key}")
            uploaded_count += 1
        except Exception as e:
            print(f"✗ Failed to upload {yaml_file_path}: {e}")
    
    if uploaded_count == 0:
        raise Exception("Failed to upload any YAML files")
    
    print(f"\n✓ Successfully uploaded {uploaded_count} file(s) to S3")

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
        echo "Converting Python DAGs to YAML..."
        
        # Create output directory
        mkdir -p /tmp/output_yaml
        rm -f /tmp/output_yaml/*.yaml  # Clean up any old files
        
        # DAG files are already synced to /usr/local/airflow/dags/
        cd /usr/local/airflow/dags
        
        # List available Python DAG files
        echo "Available Python DAG files:"
        ls -la *.py | grep -v "__" | grep -v "dag_factory_loader" | grep -v "dag_converter_pipeline" || true
        
        # Convert all Python DAG files (excluding special ones)
        for dag_file in *.py; do
            # Skip special files
            if [[ "$dag_file" == "__"* ]] || \
               [[ "$dag_file" == "dag_factory_loader.py" ]] || \
               [[ "$dag_file" == "dag_converter_pipeline.py" ]]; then
                echo "Skipping $dag_file"
                continue
            fi
            
            echo ""
            echo "Converting $dag_file..."
            if dag-converter convert "$dag_file" --output /tmp/output_yaml; then
                echo "✓ Successfully converted $dag_file"
            else
                echo "✗ Failed to convert $dag_file (may not be a valid DAG)"
            fi
        done
        
        # List the output
        echo ""
        echo "=== Conversion Results ==="
        if [ -d /tmp/output_yaml ] && [ "$(ls -A /tmp/output_yaml)" ]; then
            echo "Generated YAML files:"
            ls -lh /tmp/output_yaml/
            
            # Show content of each YAML file
            for yaml_file in /tmp/output_yaml/*.yaml; do
                if [ -f "$yaml_file" ]; then
                    echo ""
                    echo "=== Content of $(basename $yaml_file) ==="
                    head -n 50 "$yaml_file"
                    echo "..."
                fi
            done
        else
            echo "ERROR: No YAML files were generated!"
            exit 1
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
