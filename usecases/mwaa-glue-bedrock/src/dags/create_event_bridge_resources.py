from airflow import DAG
from airflow.decorators import task
from airflow.utils.dates import days_ago
from airflow.providers.amazon.aws.operators.eventbridge import EventBridgePutRuleOperator
from airflow.hooks.base import BaseHook
import requests, json, random, logging
import boto3, time, mwaa_config

# Default args for the DAG
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
}

EVENT_BRIDGE_RULE_NAME = "Salesforce_CaseChangeEvent_Rule"

# Create the DAG
with DAG(
    'create_event_bridge_resources',
    default_args=default_args,
    description='Automate Salesforce - EventBridge integration',
    catchup=False,   
    # schedule_interval = "@once",
    schedule_interval = None,
    start_date=days_ago(1),
    tags=['setup'],
) as dag:

    def get_salesforce_credentials():
        conn = BaseHook.get_connection(mwaa_config.SALESFORCE_CONNECTION)
        extras = conn.extra_dejson
        return {
            'base_url': conn.host,
            'client_id': extras['client_id'],
            'client_secret': extras['client_secret'],
            'aws_account_id': extras['aws_account_id'],
            'aws_region': extras['aws_region'].upper()
        }

    @task
    def get_access_token():
        credentials = get_salesforce_credentials()
        ACCESS_TOKEN_URL = f"{credentials['base_url']}/services/oauth2/token"

        data = {
            'grant_type': 'client_credentials',
            'client_id': credentials['client_id'],
            'client_secret': credentials['client_secret']
        }

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        response = requests.post(ACCESS_TOKEN_URL, data=data, headers=headers)

        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            raise Exception(f"Failed to get access token: {response.status_code} - {response.text}")

    def create_sfdc_resource(access_token, url_path, payload, method="POST"):
        credentials = get_salesforce_credentials()
        url = f"{credentials['base_url']}{url_path}"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }

        logging.info(f"Request URL: {url}")
        logging.info(f"Request Headers: {json.dumps(headers)}")
        logging.info(f"Request Payload: {json.dumps(payload)}")
        
        if method == "POST":
            response = requests.post(url, headers=headers, data=json.dumps(payload))
        elif method == "PATCH":
            response = requests.patch(url, headers=headers, data=json.dumps(payload))
        elif method == "DELETE":
            response = requests.delete(url, headers=headers)
        elif method == "GET":
            response = requests.get(url, headers=headers)
        elif method == "PUT":
            response = requests.put(url, headers=headers, data=json.dumps(payload))    

        logging.info(f"Response from Salesforce API: {response.status_code} - {response.text}")

        if response.status_code == 201:
            return response.json().get('id')
        elif response.status_code == 204:
            return {"status":"enabled"}
        else:
            raise Exception(f"Failed to create resource: {response.status_code} - {response.text}")

    @task
    def create_named_credential(access_token):
        credentials = get_salesforce_credentials()
        named_credential_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        full_name = f"EventBridgeNamedCredential_{named_credential_id}"

        payload = {
            "FullName": full_name,
            "Metadata": {
                "label": f"EventBridgeNamedCredential_{named_credential_id}",
                "endpoint": f"arn:aws:{credentials['aws_region']}:{credentials['aws_account_id']}",
                "principalType": "Anonymous",
                "generateAuthorizationHeader": True,
                "protocol": "NoAuthentication"
            }
        }

        resource_id = create_sfdc_resource(access_token, '/services/data/v61.0/tooling/sobjects/NamedCredential', payload)
        logging.info(f"Named Credential created with ID: {resource_id}")
        return {'id': resource_id, 'full_name': full_name}

    @task
    def create_platform_event_channel(access_token):
        platform_event_channel_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        full_name = f"EventBridge_{platform_event_channel_id}__chn"
        payload = {
            "FullName": full_name,
            "Metadata": {
                "label": f"EventBridgePlatformEventChannel_{platform_event_channel_id}",
                "channelType": "data"
            }
        }

        resource_id = create_sfdc_resource(access_token, '/services/data/v61.0/tooling/sobjects/PlatformEventChannel', payload)
        logging.info(f"Platform Event Channel created with FullName: {full_name}")
        return {'id': resource_id, 'full_name': full_name}


    @task
    def create_event_channel_member(access_token, platform_event_channel):
        event_channel_member_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        payload = {
            "FullName": f"EventBridge_channel_member_{event_channel_member_id}",
            "Metadata": {
                "eventChannel": platform_event_channel['full_name'],
                "selectedEntity": "CaseChangeEvent"
            }
        }

        # Return the Event Channel Member ID
        return create_sfdc_resource(access_token, '/services/data/v61.0/tooling/sobjects/PlatformEventChannelMember', payload)

    @task
    def create_event_relay(access_token, platform_event_channel, named_credential):
        replay_name_id = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ', k=4))
        full_name = f"EventBridge_event_relay_{replay_name_id}"
        payload = {
            "FullName": full_name,
            "Metadata": {
                "destinationResourceName": f"callout:{named_credential['full_name']}",
                "eventChannel": platform_event_channel['full_name'],
                "label": f"EventBridge {replay_name_id} Relay",
                "relayOption": "{\"ReplayRecovery\":\"LATEST\"}",
                "state": "STOP"
            }
        }
        resource_id = create_sfdc_resource(access_token, '/services/data/v61.0/tooling/sobjects/EventRelayConfig', payload)
        return {'id': resource_id, 'full_name': full_name}

    @task
    def enable_event_relay(access_token, event_relay):
        # Enable event relay
        payload = {
            "Metadata": {
                "state": "RUN"
            }
        }
        event_relay_id = event_relay['id']
        return create_sfdc_resource(access_token, f'/services/data/v61.0/tooling/sobjects/EventRelayConfig/{event_relay_id}', payload, "PATCH")
        
    @task
    def enable_pending_event_sources():
        # Get Salesforce credentials from the Airflow connection
        salesforce_conn = BaseHook.get_connection(mwaa_config.SALESFORCE_CONNECTION)
        extras = salesforce_conn.extra_dejson
        aws_region = extras['aws_region'].lower()  # Use the AWS region from the Salesforce connection. Use .lower just in case. 

        # Create a boto3 client using the default AWS connection and specified region
        aws_conn = BaseHook.get_connection('aws_default')
        session = boto3.Session(
            aws_access_key_id=aws_conn.login,
            aws_secret_access_key=aws_conn.password,
            region_name=aws_region
        )
        client = session.client('events')

        max_retries = 10  # Set the number of retries for eventual consistency
        retry_interval = 10  # Wait for 10 seconds between retries

        for retry in range(max_retries):
            # List all event sources
            response = client.list_event_sources()

            # Filter for pending sources created by aws.partner/salesforce.com
            pending_sources = [
                event_source for event_source in response['EventSources']
                if event_source['State'] == 'PENDING' and event_source['CreatedBy'] == 'aws.partner/salesforce.com'
            ]

            if pending_sources:
                # Assuming only one pending event source
                event_source_name = pending_sources[0]['Name']
                event_bus_name = event_source_name  # Name the event bus the same as the event source

                # Create the event bus with EventSourceName
                try:
                    client.create_event_bus(
                        Name=event_bus_name,
                        EventSourceName=event_source_name  # Pass the event source name
                    )
                    logging.info(f"Created Event Bus with name {event_bus_name} and EventSourceName {event_source_name}.")
                except client.exceptions.ResourceAlreadyExistsException:
                    logging.info(f"Event Bus {event_bus_name} already exists.")

                return event_bus_name

            # If no pending event sources found, wait and retry
            logging.info(f"No pending event sources found. Retrying {retry + 1}/{max_retries}...")
            time.sleep(retry_interval)

        # If after max retries, no event sources are found, raise an exception to fail the task
        raise Exception("No pending event sources found after max retries.")

    @task
    def add_lambda_to_eb(event_bus_name): 
        # Get the Airflow connection for AWS
        aws_conn = BaseHook.get_connection('aws_default')
        session = boto3.Session(
            aws_access_key_id=aws_conn.login,
            aws_secret_access_key=aws_conn.password,
        )
        lambda_client = session.client('lambda')

        # List all Lambda functions
        response = lambda_client.list_functions()

        # Call boto3 list_functions and select the lambda function with tag integration=mwaa-salesforce
        target_lambda = None
        for function in response['Functions']:
            # Get the tags for the Lambda function
            tags = lambda_client.list_tags(Resource=function['FunctionArn'])['Tags']
            
            # Check if the 'integration' tag exists and has the value 'mwaa-salesforce'
            if tags.get('integration') == 'mwaa-salesforce':
                target_lambda = function['FunctionArn']
                break  # Found the target Lambda, so we can exit the loop

        if not target_lambda:
            raise Exception("No Lambda function found with the specified tag.")

        # Add Lambda to eventBridge as a target using boto3
        eventbridge = session.client('events')
        response = eventbridge.put_targets(
            Rule=EVENT_BRIDGE_RULE_NAME,
            EventBusName=event_bus_name,
            Targets=[
                {
                    'Arn': target_lambda,
                    'Id': 'InvokeLambda'
                }
            ]
        )
        
        return target_lambda

    @task
    def add_lambda_invoke_permission(target_lambda, eb_details):
        logging.info(f"Adding Lambda invoke permission for {target_lambda}")
        logging.info(f"EB Details: {eb_details}")

        aws_conn = BaseHook.get_connection('aws_default')
        session = boto3.Session(
            aws_access_key_id=aws_conn.login,
            aws_secret_access_key=aws_conn.password,
        )
        lambda_client = session.client('lambda')

        # Extract details from the lambda_details dictionary
        rule_arn = eb_details.get('RuleArn')
        logging.info(f"Rule ARN: {rule_arn}")

        # Add permission to Lambda function
        lambda_client.add_permission(
            FunctionName=target_lambda,
            StatementId=f"AllowEventBridgeInvoke_{random.randint(1000, 9999)}",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn
        )

    access_token = get_access_token()
    named_credential = create_named_credential(access_token)
    platform_event_channel = create_platform_event_channel(access_token)
    channel_member = create_event_channel_member(access_token, platform_event_channel)
    event_relay = create_event_relay(access_token, platform_event_channel, named_credential)
    enable_relay = enable_event_relay(access_token, event_relay)
    event_bus_name = enable_pending_event_sources()
    create_eventbridge_rule_task = EventBridgePutRuleOperator(
        task_id='create_eventbridge_rule',
        name=EVENT_BRIDGE_RULE_NAME,
        event_bus_name=event_bus_name,
        event_pattern=json.dumps({
            "source": [{
                "prefix": "aws.partner/salesforce.com"
            }],
            "detail-type": ["CaseChangeEvent"],
            "detail": {
                "payload": {
                    "ChangeEventHeader": {
                        "changeType": ["CREATE"]
                    }
                }
            }
        }),
        state="ENABLED",
        aws_conn_id='aws_default'
    )

    add_target_to_event_bridge = add_lambda_to_eb(event_bus_name)
    add_permission_task = add_lambda_invoke_permission(add_target_to_event_bridge, create_eventbridge_rule_task.output)

    # Task dependencies
    access_token >> [named_credential >> platform_event_channel] >> channel_member >> event_relay >> enable_relay >> event_bus_name >> create_eventbridge_rule_task >> add_target_to_event_bridge >> add_permission_task