#!/usr/bin/env python3
"""
MWAA Data Pipeline Workshop - Deployment Script
Deploys MWAA environment with VPC, S3, Redshift Serverless, and sample DAGs
"""

import subprocess
import sys
import json
import time

STACK_NAME = "mwaa-data-pipeline-workshop"
MIN_CLI_VERSION = "1.32.80"

def run_command(command, cwd=None):
    """Execute CLI command and stream output"""
    print(f"Running: {command}")
    process = subprocess.Popen(
        command, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        shell=True, 
        cwd=cwd, 
        text=True
    )
    
    stdout_data = []
    while True:
        output = process.stdout.readline()
        if output == "" and process.poll() is not None:
            break
        if output:
            print(output.strip())
            stdout_data.append(output.strip())
    
    exit_code = process.poll()
    stderr_output = process.stderr.read().strip()
    
    if stderr_output:
        print(f"Error: {stderr_output}")
    
    if exit_code != 0:
        print(f"Command failed with exit code {exit_code}")
        sys.exit(1)
    
    return "\n".join(stdout_data)

def check_aws_cli():
    """Check AWS CLI version"""
    print("Checking AWS CLI version...")
    try:
        result = subprocess.run(['aws', '--version'], capture_output=True, text=True)
        print(f"AWS CLI: {result.stdout.strip()}")
    except FileNotFoundError:
        print("AWS CLI is not installed. Please install it first.")
        sys.exit(1)

def check_sam_cli():
    """Check SAM CLI installation"""
    print("Checking SAM CLI...")
    try:
        result = subprocess.run(['sam', '--version'], capture_output=True, text=True)
        print(f"SAM CLI: {result.stdout.strip()}")
    except FileNotFoundError:
        print("SAM CLI is not installed. Please install it:")
        print("  pip install aws-sam-cli")
        sys.exit(1)

def get_aws_region():
    """Get AWS region from user or config"""
    result = subprocess.run(
        ['aws', 'configure', 'get', 'region'],
        capture_output=True,
        text=True
    )
    default_region = result.stdout.strip() or 'us-east-1'
    
    print(f"\nCurrent AWS region: {default_region}")
    user_region = input(f"Enter region to deploy to (press Enter for {default_region}): ").strip()
    
    region = user_region if user_region else default_region
    print(f"✓ Using region: {region}")
    return region

def deploy_sam(region):
    """Deploy SAM template"""
    print("\n" + "="*60)
    print("Deploying SAM template...")
    print("="*60 + "\n")
    
    cmd = (
        f"sam build && "
        f"sam deploy --no-confirm-changeset "
        f"--stack-name {STACK_NAME} "
        f"--capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM "
        f"--region {region} "
        f"--resolve-s3"
    )
    
    run_command(cmd)
    print("\n✓ SAM deployment complete!")

def get_stack_outputs(region):
    """Get CloudFormation stack outputs"""
    print("\nFetching stack outputs...")
    outputs_json = run_command(
        f"aws cloudformation describe-stacks "
        f"--stack-name {STACK_NAME} "
        f"--query 'Stacks[0].Outputs' "
        f"--region {region}"
    )
    
    outputs = json.loads(outputs_json)
    result = {}
    for output in outputs:
        result[output['OutputKey']] = output['OutputValue']
    
    return result

def update_dag_with_outputs(bucket_name, glue_role_arn, emr_role_arn, redshift_workgroup, region):
    """Update DAG and scripts with deployment outputs"""
    print("\nUpdating files with deployment values...")
    
    # Extract role name from ARN for Glue
    glue_role_name = glue_role_arn.split('/')[-1]
    
    # Get Redshift role ARN from stack outputs
    outputs = get_stack_outputs(region)
    redshift_role_arn = outputs.get('RedshiftRoleArn', '')
    
    # Define all replacements
    replacements = {
        '{{S3_BUCKET_NAME}}': bucket_name,
        '{{GLUE_ROLE_ARN}}': glue_role_arn,
        '{{GLUE_ROLE_NAME}}': glue_role_name,
        '{{EMR_ROLE_ARN}}': emr_role_arn,
        '{{REDSHIFT_ROLE_ARN}}': redshift_role_arn,
        '{{REDSHIFT_WORKGROUP}}': redshift_workgroup,
        '{{AWS_REGION}}': region,
    }
    
    # Files to update
    files_to_update = [
        'dags/data_pipeline.py',
        'dags/data_pipeline.yaml',
        'dags/dag_converter_pipeline.py',
        'scripts/glue/nyc_raw_to_transform.py',
        'scripts/emr/nyc_aggregations.py'
    ]
    
    # Store original content
    original_content = {}
    
    for file_path in files_to_update:
        try:
            with open(file_path, 'r') as f:
                original_content[file_path] = f.read()
            
            # Apply all replacements
            content = original_content[file_path]
            for placeholder, value in replacements.items():
                content = content.replace(placeholder, value)
            
            with open(file_path, 'w') as f:
                f.write(content)
            
            print(f"  ✓ Updated {file_path}")
        except FileNotFoundError:
            print(f"  ⚠ Skipped {file_path} (not found)")
    
    print("✓ All files updated with deployment values")
    
    # Return original content for restoration
    return original_content

def restore_placeholders(original_content):
    """Restore placeholder values in files"""
    print("\nRestoring placeholders in local files...")
    
    for file_path, content in original_content.items():
        try:
            with open(file_path, 'w') as f:
                f.write(content)
            print(f"  ✓ Restored {file_path}")
        except Exception as e:
            print(f"  ⚠ Failed to restore {file_path}: {e}")
    
    print("✓ Placeholders restored")

def upload_files_to_s3(bucket_name):
    """Upload DAGs and scripts to S3"""
    print("\n" + "="*60)
    print("Uploading files to S3...")
    print("="*60 + "\n")
    
    # Note: requirements.txt already uploaded by Lambda during stack creation
    
    # Upload DAGs (Python and YAML files, excluding plugins directory)
    print("Uploading DAG files...")
    run_command(f"aws s3 sync dags/ s3://{bucket_name}/dags/ --exclude '__pycache__/*' --exclude '*.pyc'")
    
    # Upload scripts
    print("\nUploading scripts...")
    run_command(f"aws s3 sync scripts/ s3://{bucket_name}/scripts/ --exclude '__pycache__/*' --exclude '*.pyc'")
    
    
    print("\n✓ Files uploaded successfully!")

def copy_sample_data(bucket_name, region):
    """Copy sample data from workshop bucket"""
    print("\n" + "="*60)
    print("Copying sample data...")
    print("="*60 + "\n")
    
    source = "s3://ws-assets-prod-iad-r-iad-ed304a55c2ca1aee/795e88bb-17e2-498f-82d1-2104f4824168/data/raw/green/green_tripdata_2020-06.csv"
    dest = f"s3://{bucket_name}/data/raw/green/green_tripdata_2020-06.csv"
    
    print(f"Copying from: {source}")
    print(f"Copying to: {dest}")
    print(f"Target region: {region}")
    
    # Use --region flag to ensure correct target region
    run_command(f"aws s3 cp {source} {dest} --region {region}")
    print("\n✓ Sample data copied!")

def main():
    print("\n" + "="*60)
    print("MWAA Data Pipeline Workshop - Deployment")
    print("="*60 + "\n")
    
    # Pre-flight checks
    check_aws_cli()
    check_sam_cli()
    region = get_aws_region()
     
    # Deploy infrastructure
    deploy_sam(region)
    
    # Get outputs
    outputs = get_stack_outputs(region)
    bucket_name = outputs['MWAABucketName']
    glue_role_arn = outputs['GlueRoleArn']
    emr_role_arn = outputs['EMRServerlessRoleArn']
    redshift_workgroup = outputs['RedshiftWorkgroupName']
    
    # Update DAG with actual values (returns original content)
    original_content = update_dag_with_outputs(bucket_name, glue_role_arn, emr_role_arn, redshift_workgroup, region)
    
    try:
        # Upload files
        upload_files_to_s3(bucket_name)
        
        # Copy sample data
        copy_sample_data(bucket_name, region)
    finally:
        # Always restore placeholders, even if upload fails
        restore_placeholders(original_content)
    
    # Print summary
    print("\n" + "="*60)
    print("Deployment Complete!")
    print("="*60)
    print(f"\nMWAA Webserver URL: {outputs['MWAAWebserverUrl']}")
    print(f"S3 Bucket: {bucket_name}")
    print(f"Redshift Workgroup: {redshift_workgroup}")
    print(f"\nGlue Role ARN: {glue_role_arn}")
    print(f"EMR Serverless Role ARN: {emr_role_arn}")
    print(f"Redshift Role ARN: {outputs['RedshiftRoleArn']}")
    print("\nNext steps:")
    print("1. Wait 20-30 minutes for MWAA environment to be ready")
    print("2. Access the Airflow UI using the webserver URL above")
    print("3. The 'immersion_day_data_pipeline' DAG will be available")
    print("4. Enable and trigger the DAG to run the pipeline")
    print(f"\n💡 Tip: Run 'python3 cleanup.py' when done to avoid charges")
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    main()
