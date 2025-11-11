#!/usr/bin/env python3
"""
MWAA Data Pipeline Workshop - Cleanup Script
Deletes all resources created by the deployment
"""

import subprocess
import sys
import json

STACK_NAME = "mwaa-data-pipeline-workshop"

def run_command(command):
    """Execute CLI command"""
    print(f"Running: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr and result.returncode != 0:
        print(f"Error: {result.stderr}")
    return result.returncode == 0

def get_stack_outputs(region):
    """Get CloudFormation stack outputs"""
    result = subprocess.run(
        f"aws cloudformation describe-stacks --stack-name {STACK_NAME} --query 'Stacks[0].Outputs' --region {region}",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        return None
    
    try:
        outputs = json.loads(result.stdout)
        if not outputs:
            return None
            
        result_dict = {}
        for output in outputs:
            result_dict[output['OutputKey']] = output['OutputValue']
        
        return result_dict
    except (json.JSONDecodeError, TypeError):
        return None

def empty_s3_bucket(bucket_name):
    """Empty S3 bucket before deletion"""
    print(f"\nEmptying S3 bucket: {bucket_name}")
    
    # Delete all objects
    print("  Deleting objects...")
    run_command(f"aws s3 rm s3://{bucket_name} --recursive")
    
    # Delete all versions (if versioning is enabled)
    print("  Deleting object versions...")
    result = subprocess.run(
        f"aws s3api list-object-versions --bucket {bucket_name} --output json",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and result.stdout:
        import json
        try:
            versions = json.loads(result.stdout)
            
            # Delete versions
            if 'Versions' in versions:
                for version in versions['Versions']:
                    key = version['Key']
                    version_id = version['VersionId']
                    run_command(f"aws s3api delete-object --bucket {bucket_name} --key '{key}' --version-id {version_id}")
            
            # Delete delete markers
            if 'DeleteMarkers' in versions:
                for marker in versions['DeleteMarkers']:
                    key = marker['Key']
                    version_id = marker['VersionId']
                    run_command(f"aws s3api delete-object --bucket {bucket_name} --key '{key}' --version-id {version_id}")
        except json.JSONDecodeError:
            pass
    
    print("✓ S3 bucket emptied")

def delete_glue_crawlers(region):
    """Delete Glue crawlers created by the pipeline"""
    print("\nDeleting Glue crawlers...")
    
    # List all Glue crawlers
    result = subprocess.run(
        f"aws glue get-crawlers --region {region} --output json",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and result.stdout:
        try:
            crawlers_data = json.loads(result.stdout)
            crawlers = crawlers_data.get('Crawlers', [])
            
            # Delete crawlers that match our pipeline naming pattern
            deleted_count = 0
            for crawler in crawlers:
                crawler_name = crawler['Name']
                if 'airflow-workshop' in crawler_name or 'immersion_day' in crawler_name.lower():
                    print(f"  Deleting Glue crawler: {crawler_name}")
                    run_command(f"aws glue delete-crawler --name {crawler_name} --region {region}")
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"✓ Deleted {deleted_count} Glue crawler(s)")
            else:
                print("  No matching Glue crawlers found")
        except json.JSONDecodeError:
            print("  Could not parse Glue crawlers list")
    else:
        print("  Could not list Glue crawlers")

def delete_glue_tables(region, database_name='default'):
    """Delete Glue tables created by the pipeline"""
    print(f"\nDeleting Glue tables from database '{database_name}'...")
    
    # List all tables in the database
    result = subprocess.run(
        f"aws glue get-tables --database-name {database_name} --region {region} --output json",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and result.stdout:
        try:
            tables_data = json.loads(result.stdout)
            tables = tables_data.get('TableList', [])
            
            # Delete tables that match our pipeline naming pattern
            deleted_count = 0
            for table in tables:
                table_name = table['Name']
                # Delete tables created by the crawler (green tripdata tables)
                if 'green' in table_name.lower() or 'tripdata' in table_name.lower():
                    print(f"  Deleting Glue table: {table_name}")
                    run_command(f"aws glue delete-table --database-name {database_name} --name {table_name} --region {region}")
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"✓ Deleted {deleted_count} Glue table(s)")
            else:
                print("  No matching Glue tables found")
        except json.JSONDecodeError:
            print("  Could not parse Glue tables list")
    else:
        print(f"  Could not list Glue tables (database '{database_name}' may not exist)")

def delete_glue_jobs(region):
    """Delete Glue jobs created by the pipeline"""
    print("\nDeleting Glue jobs...")
    
    # List all Glue jobs
    result = subprocess.run(
        f"aws glue get-jobs --region {region} --output json",
        shell=True,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0 and result.stdout:
        try:
            jobs_data = json.loads(result.stdout)
            jobs = jobs_data.get('Jobs', [])
            
            # Delete jobs that match our pipeline naming pattern
            deleted_count = 0
            for job in jobs:
                job_name = job['Name']
                # Delete jobs created by the pipeline (adjust pattern as needed)
                if 'nyc_raw_to_transform' in job_name or 'immersion_day' in job_name.lower():
                    print(f"  Deleting Glue job: {job_name}")
                    run_command(f"aws glue delete-job --job-name {job_name} --region {region}")
                    deleted_count += 1
            
            if deleted_count > 0:
                print(f"✓ Deleted {deleted_count} Glue job(s)")
            else:
                print("  No matching Glue jobs found")
        except json.JSONDecodeError:
            print("  Could not parse Glue jobs list")
    else:
        print("  Could not list Glue jobs")

def delete_stack(region):
    """Delete CloudFormation stack"""
    print(f"\nDeleting CloudFormation stack: {STACK_NAME}")
    run_command(f"aws cloudformation delete-stack --stack-name {STACK_NAME} --region {region}")
    print("✓ Stack deletion initiated")
    print("\nWaiting for stack deletion to complete...")
    run_command(f"aws cloudformation wait stack-delete-complete --stack-name {STACK_NAME} --region {region}")
    print("✓ Stack deleted successfully")

def get_aws_region():
    """Get AWS region with auto-detection"""
    # Try to get region from SAM config first
    detected_region = None
    try:
        with open('samconfig.toml', 'r') as f:
            for line in f:
                if 'region' in line and '=' in line:
                    detected_region = line.split('=')[1].strip().strip('"').strip("'")
                    if detected_region:
                        break
    except FileNotFoundError:
        pass
    
    # Try to get region from deployed stack if not found
    if not detected_region:
        result = subprocess.run(
            f"aws cloudformation describe-stacks --stack-name {STACK_NAME} --query 'Stacks[0].StackId' --output text 2>/dev/null",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            stack_arn = result.stdout.strip()
            detected_region = stack_arn.split(':')[3]
    
    # Fall back to AWS CLI config
    if not detected_region:
        result = subprocess.run(
            ['aws', 'configure', 'get', 'region'],
            capture_output=True,
            text=True
        )
        detected_region = result.stdout.strip() or 'us-east-1'
    
    print(f"\nDetected region: {detected_region}")
    user_region = input(f"Press Enter to use {detected_region}, or type a different region: ").strip()
    
    region = user_region if user_region else detected_region
    print(f"✓ Using region: {region}")
    return region

def main():
    print("\n" + "="*60)
    print("MWAA Data Pipeline Workshop - Cleanup")
    print("="*60 + "\n")
    
    # Get region automatically
    region = get_aws_region()
    
    # Confirm deletion
    print("\n⚠️  WARNING: This will delete all resources!")
    response = input("Are you sure you want to continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Cleanup cancelled.")
        sys.exit(0)
    
    # Get stack outputs
    outputs = get_stack_outputs(region)
    
    if not outputs:
        print("\n⚠️  Could not find stack outputs.")
        print("The stack may not exist or may already be deleted.")
        response = input("Do you want to try deleting Glue resources anyway? (yes/no): ")
        if response.lower() == 'yes':
            delete_glue_crawlers(region)
            delete_glue_tables(region, 'default')
            delete_glue_jobs(region)
        print("\nNothing else to clean up.")
        sys.exit(0)
    
    # Delete Glue resources first (before stack deletion)
    delete_glue_crawlers(region)
    delete_glue_tables(region, 'default')
    delete_glue_jobs(region)
    
    # Empty S3 bucket
    if 'MWAABucketName' in outputs:
        bucket_name = outputs['MWAABucketName']
        empty_s3_bucket(bucket_name)
    else:
        print("⚠️  Could not find bucket name in stack outputs.")
    
    # Delete stack
    delete_stack(region)
    
    print("\n" + "="*60)
    print("Cleanup Complete!")
    print("="*60)
    print("\nAll resources have been deleted.")
    print("You will no longer incur charges for this workshop.\n")

if __name__ == "__main__":
    main()
