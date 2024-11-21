# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
import json
import urllib.parse
import boto3
import requests
import os

print('Loading function')

s3 = boto3.client('s3')

MWAA_ENV = os.getenv('MWAA_ENV')
REGION = os.getenv('MWAA_AWS_REGION')

# Object in Salesforce
DATASET_NAME = 'CaseChangeEvent'

def get_session_info(region, env_name):
    try:
        # Initialize MWAA client and request a web login token
        mwaa = boto3.client('mwaa', region_name=region)
        response = mwaa.create_web_login_token(Name=env_name)
        
        # Extract the web server hostname and login token
        web_server_host_name = response["WebServerHostname"]
        web_token = response["WebToken"]
        
        # Construct the URL needed for authentication 
        login_url = f"https://{web_server_host_name}/aws_mwaa/login"
        login_payload = {"token": web_token}

        # Make a POST request to the MWAA login url using the login payload
        response = requests.post(
            login_url,
            data=login_payload,
            timeout=10
        )

        # Check if login was succesfull 
        if response.status_code == 200:
        
            # Return the hostname and the session cookie 
            return (
                web_server_host_name,
                response.cookies["session"]
            )
        else:
            # Log an error
            print("Failed to log in: HTTP %d", response.status_code)
            return None
    except requests.RequestException as e:
         # Log any exceptions raised during the request to the MWAA login endpoint
        print("Request failed: %s", str(e))
        return None
    except Exception as e:
        # Log any other unexpected exceptions
        print("An unexpected error occurred: %s", str(e))
        return None

def trigger_dataset(region, env_name, dataset_name, config):
    print(f"Attempting to Create dataset event {dataset_name} in environment {env_name} at region {region}")

    # Retrieve the web server hostname and session cookie for authentication
    try:
        web_server_host_name, session_cookie = get_session_info(region, env_name)
        if not session_cookie:
            print("Authentication failed, no session cookie retrieved.")
            return
    except Exception as e:
        print(f"Error retrieving session info: {str(e)}")
        return

    # Prepare headers and payload for the request
    cookies = {"session": session_cookie}
    json_body = {
        "dataset_uri": dataset_name,
        "extra": config
    }

    # Construct the URL for triggering the dataset
    url = f"https://{web_server_host_name}/api/v1/datasets/events"

    # Send the POST request to trigger the DAG
    try:
        response = requests.post(url, cookies=cookies, json=json_body)
        # Check the response status code to determine if the DAG was triggered successfully
        if response.status_code == 200:
            print("dataset triggered successfully.")
        else:
            print(f"Failed to trigger dataset: HTTP {response.status_code} - {response.text}")
    except requests.RequestException as e:
        print(f"Request to trigger DAG failed: {str(e)}")

def lambda_handler(event, context):
    print("Received event: " + json.dumps(event, indent=2))
    try:
        trigger_dataset(region=REGION, env_name=MWAA_ENV, dataset_name=DATASET_NAME, config=event)
        
        return
    except Exception as e:
        print(e)
        raise e
              
