import sys
import boto3
import requests
import subprocess
import json
import stack_config 

# Salesforce URL and API version
SALESFORCE_API_VERSION = stack_config.SALESFORCE_API_VERSION
STACK_NAME = stack_config.STACK_NAME

# Function to execute CLI commands
def run_cli_command(command, cwd=None):
    print(f"Running command: {command}")
    
    # Initialize variables to capture stdout and stderr
    stdout_data = []
    stderr_data = []
    
    # Run the command and capture both stdout and stderr in real-time
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, cwd=cwd, text=True)
    
    # Stream output in real-time
    while True:
        # Read line-by-line from stdout
        output = process.stdout.readline()
        if output == "" and process.poll() is not None:
            break
        if output:
            print(output.strip())  # Print the output of the command as it happens
            stdout_data.append(output.strip())  # Store the output in a list

    # Capture the final exit code of the command
    exit_code = process.poll()

    # Capture and print stderr if any errors occurred
    stderr_output = process.stderr.read().strip()
    if stderr_output:
        print(stderr_output)
        stderr_data.append(stderr_output)
    
    # Return the stdout as a single string, joining the lines
    return "\n".join(stdout_data)

# Retrieve Salesforce credentials from AWS Secrets Manager
def get_salesforce_credentials(secret_name, region):
    print(f"Retrieving Salesforce credentials from Secrets Manager: {secret_name}")
    try:
        session = boto3.session.Session()
        client = session.client(service_name="secretsmanager", region_name=region)
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        secret = json.loads(get_secret_value_response["SecretString"])
        return secret["USER_MANAGED_CLIENT_APPLICATION_CLIENT_ID"], secret["USER_MANAGED_CLIENT_APPLICATION_CLIENT_SECRET"]
    except Exception as e:
        print(f"Error retrieving secret: {e}")
        sys.exit(1)

# Function to get an access token using client credentials flow
def get_access_token(client_id, client_secret, sfdc_base_url):
    data = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    response = requests.post(f"{sfdc_base_url}/services/oauth2/token", data=data, headers=headers)

    if response.status_code == 200:
        response_data = response.json()
        return response_data.get('access_token')
    else:
        print(f'Error fetching access token: {response.status_code} - {response.text}')
        return None

# Function to list Salesforce resources
def list_sfdc_resources(url_path, access_token, sfdc_base_url):
    url = f"{sfdc_base_url}{url_path}"
    headers = {
        'Authorization': f"Bearer {access_token}"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        print(f'Error fetching resources: {response.status_code} - {response.text}')
        return None

# Function to delete Salesforce resources
def delete_sfdc_resource(url_path, resource_id, access_token, sfdc_base_url):
    url = f"{sfdc_base_url}{url_path}{resource_id}"
    headers = {
        'Authorization': f"Bearer {access_token}"
    }

    response = requests.delete(url, headers=headers)
    if response.status_code == 204:
        print(f'Successfully deleted resource with id {resource_id}')
        return True
    else:
        print(f'Error deleting resource {resource_id}: {response.status_code} - {response.text}')
        return False

# Function to delete a connected app by name
def delete_connected_app(app_name, access_token, sfdc_base_url):
    query = f"SELECT Id, Name FROM ConnectedApplication WHERE Name='{app_name}' LIMIT 1"
    connected_app_data = list_sfdc_resources(f"/services/data/{SALESFORCE_API_VERSION}/tooling/query/?q={query}", access_token, sfdc_base_url)

    if connected_app_data and connected_app_data['totalSize'] > 0:
        connected_app_id = connected_app_data['records'][0]['Id']
        print(f'Found Connected App: {app_name} with Id: {connected_app_id}')
        if delete_sfdc_resource(f"/services/data/{SALESFORCE_API_VERSION}/tooling/sobjects/ConnectedApplication/", connected_app_id, access_token, sfdc_base_url):
            print(f'Successfully deleted connected app: {app_name}')
        else:
            print(f'Failed to delete connected app: {app_name}')
    else:
        print(f'Connected App with name "{app_name}" not found.')

# Function to delete targets from a rule
def delete_targets_for_rule(rule_name, bus_name, region):
    # List targets for the rule
    list_targets_command = f"aws events list-targets-by-rule --rule {rule_name} --event-bus-name {bus_name} --region {region}"
    targets_output = run_cli_command(list_targets_command)

    # Extract target IDs from the output
    target_ids = [line.split('"')[3] for line in targets_output.splitlines() if '"Id":' in line]

    # Remove each target from the rule
    if target_ids:
        target_ids_str = " ".join(target_ids)
        remove_targets_command = f"aws events remove-targets --rule {rule_name} --event-bus-name {bus_name} --ids {target_ids_str} --region {region}"
        run_cli_command(remove_targets_command)
        print(f"Removed targets {target_ids_str} from rule: {rule_name}")

# Function to delete rules from an event bus
def delete_rules_for_event_bus(bus_name, region):
    # List rules for the event bus
    list_rules_command = f"aws events list-rules --event-bus-name {bus_name} --region {region}"
    rules_output = run_cli_command(list_rules_command)

    # Extract rule names from the output
    rule_names = [line.split('"')[3] for line in rules_output.splitlines() if '"Name":' in line]

    # Remove targets and then delete each rule
    for rule_name in rule_names:
        print(f"Processing rule: {rule_name} for event bus: {bus_name}")

        # First, remove any targets associated with the rule
        delete_targets_for_rule(rule_name, bus_name, region)

        # Then, delete the rule
        delete_rule_command = f"aws events delete-rule --name {rule_name} --event-bus-name {bus_name} --region {region} --force"
        run_cli_command(delete_rule_command)
        print(f"Deleted rule: {rule_name} from event bus: {bus_name}")

# Function to delete EventBridge event buses that start with 'aws.partner/salesforce.com/'
def delete_salesforce_event_buses(region):
    # List all event buses
    list_buses_command = f"aws events list-event-buses --region {region}"
    buses_output = run_cli_command(list_buses_command)

    # Filter event buses starting with 'aws.partner/salesforce.com/'
    event_buses = [bus for bus in buses_output.splitlines() if 'aws.partner/salesforce.com/' in bus]

    # Delete rules and then delete each filtered event bus
    for bus in event_buses:
        bus_name = bus.split('"')[3]  # Extract the event bus name
        print(f"Processing event bus: {bus_name}")

        # First, delete all rules associated with the event bus
        delete_rules_for_event_bus(bus_name, region)

        # Then delete the event bus
        delete_bus_command = f"aws events delete-event-bus --name {bus_name} --region {region}"
        run_cli_command(delete_bus_command)
        print(f"Deleted event bus: {bus_name}")

# Function to list CloudFormation stack outputs
def list_stack_outputs(stack_name, region, prefix=""):
    # Command to list all S3 buckets starting with "eb-mwaa-glue"
    list_buckets_command = f"aws s3api list-buckets --query 'Buckets[?starts_with(Name, `{STACK_NAME}`)].Name' --region {region}"
    buckets_json = run_cli_command(list_buckets_command)
    
    # Parse the JSON output
    s3_buckets = json.loads(buckets_json)
    return s3_buckets

# Function to empty an S3 bucket, including all versions
def empty_s3_bucket(bucket_name, region):
    print(f"Emptying S3 bucket: {bucket_name}")

    # Step 1: Delete all objects recursively
    delete_all_objects_command = f"aws s3 rm s3://{bucket_name} --recursive --region {region}"
    run_cli_command(delete_all_objects_command)
    print(f"Deleted all objects in bucket: {bucket_name} recursively.")

    # Step 2: Remove all versions in the bucket, if any
    list_object_versions_command = f"""aws s3api list-object-versions --bucket {bucket_name} --query 'Versions[].{{
        Key: Key,
        VersionId: VersionId
    }}' --region {region}"""
    versions_json = run_cli_command(list_object_versions_command)
    
    # Attempt to parse the versions JSON
    try:
        versions = json.loads(versions_json) or []
    except json.JSONDecodeError:
        print(f"Failed to parse object versions for bucket: {bucket_name}. Skipping version deletion.")
        versions = []

    # Iterate over versions and delete each one
    for version in versions:
        delete_command = f"aws s3api delete-object --bucket {bucket_name} --key {version['Key']} --version-id {version['VersionId']} --region {region}"
        run_cli_command(delete_command)

    # Step 3: Remove any delete markers (in case of versioned delete markers)
    list_delete_markers_command = f"""aws s3api list-object-versions --bucket {bucket_name} --query 'DeleteMarkers[].{{
        Key: Key,
        VersionId: VersionId
    }}' --region {region}"""
    delete_markers_json = run_cli_command(list_delete_markers_command)
    
    # Attempt to parse the delete markers JSON
    try:
        delete_markers = json.loads(delete_markers_json) or []
    except json.JSONDecodeError:
        print(f"Failed to parse delete markers for bucket: {bucket_name}. Skipping delete marker removal.")
        delete_markers = []

    # Iterate over delete markers and remove them
    for marker in delete_markers:
        delete_marker_command = f"aws s3api delete-object --bucket {bucket_name} --key {marker['Key']} --version-id {marker['VersionId']} --region {region}"
        run_cli_command(delete_marker_command)

    print(f"Emptied bucket: {bucket_name}")

# Function to delete the CloudFormation stack
def delete_cloudformation_stack(stack_name, region):
    print(f"Deleting CloudFormation stack: {stack_name}")
    
    # Delete the stack
    delete_stack_command = f"aws cloudformation delete-stack --stack-name {stack_name} --region {region}"
    run_cli_command(delete_stack_command)
    print(f"CloudFormation stack {stack_name} deletion initiated.")

# Main function to handle the CloudFormation stack deletion, including S3 bucket handling
def handle_cloudformation_deletion(stack_name, region):
    # Step 1: List the stack outputs and identify S3 buckets
    s3_buckets = list_stack_outputs(stack_name, region)
    print(f"Emptying Buckets {s3_buckets}")
    
    # Step 2: Empty each identified S3 bucket
    for bucket in s3_buckets:
        empty_s3_bucket(bucket, region)

        print(f"Deleting S3 bucket: {bucket}")
        delete_bucket_cmd = f"aws s3 rb s3://{bucket} --region {region}"
        run_cli_command(delete_bucket_cmd)

    # Step 3: Delete the CloudFormation stack
    delete_cloudformation_stack(stack_name, region)

# Function to display a warning message and prompt the user for confirmation
def warn_and_confirm(warning_message):
    print(warning_message)
    
    # Get user confirmation
    user_input = input().strip().lower()
    
    # If the user doesn't confirm, exit the script
    if user_input != 'yes':
        print("Execution aborted by the user.")
        sys.exit(0)
    else:
        print("Proceeding with resource deletion...")

# Main function
def main(salesforce_domain, region):
    # Display warning and confirm
    warning_message = f"""
    WARNING! Executing this script will delete all resources, including:
    - Salesforce Connected App
    - Salesforce Named Credential
    - Event Relay Configurations
    - ALL Event Buses that contain 'aws.partner/salesforce.com'
    - The CloudFormation stack: '{STACK_NAME}'
    
    This action is irreversible and will result in the permanent loss of resources.
    Do you wish to proceed? (yes/no): 
    """    
    warn_and_confirm(warning_message)

    # Try to get client_id and client_secret from environment variables if not provided
    client_id, client_secret = get_salesforce_credentials("glue/connections/salesforce_connection", region)

    #### Glue / EventBridge Resources #####
    # Delete Glue resources if they exist:
    run_cli_command(f"aws glue --region {region} delete-connection --connection-name salesforce_connection")

    # Delete Glue jobs
    
    jobs = run_cli_command(f"aws glue --region {region} list-jobs --query 'JobNames[?starts_with(@, `{STACK_NAME}`)]'")
    for job in json.loads(jobs):
        run_cli_command(f"aws glue --region {region} delete-job --job-name {job}")
    
    # Delete partner event busses.
    delete_salesforce_event_buses(region)

    # Final step: Handle the CloudFormation stack deletion
    handle_cloudformation_deletion(STACK_NAME, region)

    #### DELETE SFDC Resources #####

    
    sfdc_base_url = salesforce_domain


    if not client_id or not client_secret:
        print("Error: Salesforce Client ID and/or Client Secret not provided.")
        sys.exit(1)

    # Get access token using client credentials
    access_token = get_access_token(client_id, client_secret, sfdc_base_url)
    if access_token:
        print(f'Access token: {access_token}')
    else:
        print("Failed to retrieve access token. Skipping Salesforce delete resources")
        
    if access_token: 
        # Deleting EventRelayConfig records
        event_relays = list_sfdc_resources(f"/services/data/{SALESFORCE_API_VERSION}/tooling/query/?q=SELECT FIELDS(ALL) FROM EventRelayConfig LIMIT 200", access_token, sfdc_base_url)
        if event_relays:
            event_relay_ids = [record['Id'] for record in event_relays['records']]
            for event_relay_id in event_relay_ids:
                delete_sfdc_resource(f"/services/data/{SALESFORCE_API_VERSION}/tooling/sobjects/EventRelayConfig/", event_relay_id, access_token, sfdc_base_url)

        # Deleting the connected app 'AWSEventBridgeConnectedApp'
        delete_connected_app('AWSEventBridgeConnectedApp', access_token, sfdc_base_url)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py <SalesforceOrg Alias> <AWS Region Id>")
        sys.exit(1)

    salesforce_domain = sys.argv[1]
    # Check if salesforce_domain starts with http:// or https://, if not prepend https://
    if not salesforce_domain.startswith(('http://', 'https://')):
        salesforce_domain = f"https://{salesforce_domain}"
    

    region = sys.argv[2] if len(sys.argv) > 2 else None


    main(salesforce_domain, region)

    print("CloudFormation Template Deletion initiated. Please check on the AWS console and verify it completes.")