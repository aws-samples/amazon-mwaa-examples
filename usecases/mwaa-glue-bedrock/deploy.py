import os
import subprocess
import xml.etree.ElementTree as ET
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import datetime, time
from pathlib import Path
import sys, random, string, base64, jwt, requests, json, re
import stack_config

# Static Configurations
STACK_NAME = stack_config.STACK_NAME
SALESFORCE_APP_NAME = stack_config.SALESFORCE_APP_NAME
MIN_CLI_VERSION = stack_config.MIN_CLI_VERSION

#################### PoLP WARNING #########################
# For demonstration, we use the System Adminstrator profile, 
# in order to avoid manual approval process.
# Refer to: https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_jwt_flow.htm&type=5
#
# This script will create a Connected App with oAuth policy that states 
# "Admin approved users are pre-authorized"
#
# IMPORTANT: This is purley for demonstration purposes. 
# Scope down the user profiles for product use cases
SALESFORCE_PROFILE = "System Administrator"
#######################################################


# Function to check AWS CLI version
def check_aws_cli_version():
    print("Checking AWS CLI version...")

    # Run the command to get the AWS CLI version
    try:
        result = subprocess.run(['aws', '--version'], capture_output=True, text=True)
        version_output = result.stdout.strip()

        # Use regex to extract the version number
        version_match = re.search(r'aws-cli/(\d+\.\d+\.\d+)', version_output)
        
        if version_match:
            installed_version = version_match.group(1)
            print(f"AWS CLI version detected: {installed_version}")
            
            # Compare installed and required versions
            if compare_versions(installed_version, MIN_CLI_VERSION):
                print(f"AWS CLI version is sufficient (>= {MIN_CLI_VERSION}).")
            else:
                print(f"AWS CLI version is too old. Please upgrade to version {MIN_CLI_VERSION} or later.")
                print("To upgrade AWS CLI, run the following command:")
                print("   pip install --upgrade awscli")
                sys.exit(1)
        else:
            print("Failed to detect AWS CLI version.")
            sys.exit(1)
    except FileNotFoundError:
        print("AWS CLI is not installed. Please install it first.")
        sys.exit(1)

# Helper function to compare versions
def compare_versions(installed_version, required_version=MIN_CLI_VERSION):
    installed_version_parts = list(map(int, installed_version.split(".")))
    required_version_parts = list(map(int, required_version.split(".")))

    # Compare version parts
    for i in range(len(required_version_parts)):
        if installed_version_parts[i] > required_version_parts[i]:
            return True
        elif installed_version_parts[i] < required_version_parts[i]:
            return False
    return True

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
        print(f"Error: {stderr_output}")
        stderr_data.append(stderr_output)

    if exit_code != 0:
        print(f"Command failed with exit code {exit_code}. Exiting...")
        sys.exit(1)
    
    # Return the stdout as a single string, joining the lines
    return "\n".join(stdout_data)

# Generate random consumer key and secret
def generate_consumer_key_and_secret():
    print("Generating random Consumer Key and Consumer Secret...")
    consumer_key = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    consumer_secret = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    print(f"Consumer Key: {consumer_key}")
    print(f"Consumer Secret: {consumer_secret}")
    return consumer_key, consumer_secret

# Generate PEM Key (Private & Public Key)
def generate_pem_keys_with_cert(private_key_path="cert/key.pem", cert_path="cert/cert.pem"):
    print("Generating RSA private key and self-signed certificate...")
    Path(private_key_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cert_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
        backend=default_backend()
    )

    # Create a self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"My Company"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"mycompany.com"),
    ])
    
    certificate = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        # Certificate valid for 10 years
        datetime.datetime.utcnow() + datetime.timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName(u"mycompany.com")]),
        critical=False
    ).sign(private_key, hashes.SHA256(), default_backend())

    # Write private key to PEM file
    with open(private_key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Write certificate to PEM file
    with open(cert_path, "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))

    print(f"Private key saved to: {private_key_path}")
    print(f"Certificate saved to: {cert_path}")

    return private_key_path, cert_path

# Login to Salesforce Org
def login_to_org(salesforce_domain):
    print(f"Logging in to Salesforce Org '{salesforce_domain}'...")
    run_cli_command(f"sfdx force:auth:web:login -a {salesforce_domain}", cwd="src")

# Fetch Salesforce User ID
def fetch_salesforce_user_id(username, salesforce_domain):
    print(f"Fetching Salesforce User ID for username '{username}'...")
    query = f"SELECT Id FROM User WHERE Username = '{username}'"
    result = run_cli_command(f"sfdx force:data:soql:query -q \"{query}\" -o {salesforce_domain}", cwd="src")
    
    # Split the result into lines and get the second line which contains the User ID
    result_lines = result.splitlines()
    
    # The second non-header line should contain the ID
    user_id = result_lines[2].strip() if len(result_lines) > 2 else None
    
    if user_id and len(user_id) == 18:  # Salesforce IDs are 18 characters long
        print(f"Salesforce User ID: {user_id}")
    else:
        print("User ID not found or invalid.")
        sys.exit(1)
    
    return user_id

# Deploy the Serverless Application Model stack
def deploy_sam(salesforce_domain, consumer_key, consumer_secret, jwt_token, private_key_path, public_key_path, region, sam_s3):
    # Constructing SAM  
    cmd = (
        f"sam build && "
        f"sam deploy --no-confirm-changeset --stack-name {STACK_NAME} "
        f"--capabilities CAPABILITY_IAM --region {region} "
        f"--s3-bucket {sam_s3} "
        f"--parameter-overrides SalesforceInstanceUrl={salesforce_domain} "
        f"SalesforceClientId={consumer_key} SalesforceClientSecret={consumer_secret} SalesforceJwtToken={jwt_token} SalesforcePrivateKeyPath={private_key_path} SalesforcePublicKeyPath={public_key_path}"
    )
    # Run the SAM deploy command
    run_cli_command(cmd)

def parse_cfn_outputs(region, stack_name=STACK_NAME): 
    # Fetch CloudFormation outputs
    outputs_json = run_cli_command(
        f"aws cloudformation describe-stacks --stack-name {stack_name} --query 'Stacks[0].Outputs' --region {region}"
    )
    
    # Parse the outputs as JSON
    try:
        outputs = json.loads(outputs_json)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        sys.exit(1)    

    artifacts = {}

    for output in outputs:
        artifacts[output['OutputKey']] = output['OutputValue']

    return artifacts

# Copy files to the respective S3 buckets
def copy_files_to_s3(artifact_bucket, mwaa_env_bucket):
    print("Copying write_case_comments.py to the artifact bucket...")
    run_cli_command(f"aws s3 cp src/glue/write_case_comments.py s3://{artifact_bucket}/glue/write_case_comments.py")

    print("Copying cases to the artifact bucket...")
    run_cli_command(f"aws s3 cp src/glue/support_cases.json s3://{artifact_bucket}/cases/support_cases.json")
    
    print("Copying DAG files to the MWAA environment bucket...")
    run_cli_command(f"aws s3 cp src/dags/ s3://{mwaa_env_bucket}/dags/ --recursive")

    print("Copying PEM certificates to MWAA environment bucket...")
    run_cli_command(f"aws s3 cp cert/ s3://{mwaa_env_bucket}/cert/ --recursive")

# Create an S3 bucket for SAM
def create_sam_s3_bucket(region):
    # Generate a random bucket name
    bucket_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    bucket_name = f"{STACK_NAME}-aws-sam-cli-{bucket_suffix}"

    # Only include if region is not us-east-1
    lc = ""
    if region != "us-east-1":
        lc = f"--create-bucket-configuration LocationConstraint={region}"

    create_bucket_cmd = (
        f"aws s3api create-bucket --bucket {bucket_name} {lc}"
    )

    run_cli_command(create_bucket_cmd)
    print(f"Bucket '{bucket_name}' created successfully.")

    return bucket_name

# Create XML definition of Connected App for deployment with Salesforce CLI.
def create_connected_app_xml(salesforce_domain, username, user_id, public_key_path, consumer_key, consumer_secret, aws_region_id):
    print(f"Creating XML for the Connected App '{SALESFORCE_APP_NAME}'...")
    connected_app_xml_path = f"src/salesforce/force-app/main/default/connectedApps/{SALESFORCE_APP_NAME}.connectedApp-meta.xml"
    Path(connected_app_xml_path).parent.mkdir(parents=True, exist_ok=True)
    
    tree = ET.Element("ConnectedApp", xmlns="http://soap.sforce.com/2006/04/metadata")
    
    contact_email = ET.SubElement(tree, "contactEmail")
    contact_email.text = username
    
    label = ET.SubElement(tree, "label")
    label.text = SALESFORCE_APP_NAME
    
    #Setting a connected app Profile
    label = ET.SubElement(tree, "profileName")
    label.text = SALESFORCE_PROFILE 

    # Setting up OAuthConfig
    oauth_config = ET.SubElement(tree, "oauthConfig")
    
    oauth_client_cred_user = ET.SubElement(oauth_config, "oauthClientCredentialUser")
    oauth_client_cred_user.text = user_id
    
    is_code_cred_enabled = ET.SubElement(oauth_config, "isCodeCredentialEnabled")
    is_code_cred_enabled.text = "true"
    
    is_client_cred_enabled = ET.SubElement(oauth_config, "isClientCredentialEnabled")
    is_client_cred_enabled.text = "true"
    
    certificate = ET.SubElement(oauth_config, "certificate")
    with open(public_key_path, 'r') as pem_file:
        certificate.text = pem_file.read()
    
    consumer_key_tag = ET.SubElement(oauth_config, "consumerKey")
    consumer_key_tag.text = consumer_key
    
    consumer_secret_tag = ET.SubElement(oauth_config, "consumerSecret")
    consumer_secret_tag.text = consumer_secret
    
    # Enable Admin Authorization
    admin_authorization = ET.SubElement(oauth_config, "isAdminApproved")
    admin_authorization.text = "true"         

    # Enable JWT Token    
    is_named_user_jwt_enabled = ET.SubElement(oauth_config, "isNamedUserJwtEnabled")
    is_named_user_jwt_enabled.text = "true"
    
    scopes = ["Basic", "OpenID", "Api", "RefreshToken", "OfflineAccess"]
    for scope in scopes:
        scope_tag = ET.SubElement(oauth_config, "scopes")
        scope_tag.text = scope
    
    callback_url = ET.SubElement(oauth_config, "callbackUrl")
    callback_url.text = f"https://{aws_region_id}.console.aws.amazon.com/gluestudio/oauth"
    
    is_pkce_required = ET.SubElement(oauth_config, "isPkceRequired")
    is_pkce_required.text = "false"
    
    is_consumer_secret_optional = ET.SubElement(oauth_config, "isConsumerSecretOptional")
    is_consumer_secret_optional.text = "false"
    
    description = ET.SubElement(tree, "description")
    description.text = "A connected app to integrate with AWS EventBridge."
    
    # Write the XML tree to a file
    tree = ET.ElementTree(tree)
    with open(connected_app_xml_path, "wb") as files:
        tree.write(files)
     
    print(f"Connected App XML created at: {connected_app_xml_path}")
    return connected_app_xml_path

# Create Salesforce Project
def create_sfdc_project():
    print("Creating Salesforce project 'salesforce'...")
    run_cli_command("sfdx force:project:create -n salesforce", cwd="src")

# Clean up default project files
def clean_up_default_files():
    print("Cleaning up default project files...")
    run_cli_command("rm -rf src/salesforce")

# Deploy the project from the correct directory
def deploy_project(salesforce_domain):
    print(f"Deploying project to Salesforce Org '{salesforce_domain}' from the 'salesforce' directory...")
    run_cli_command(f"sfdx project deploy start -o {salesforce_domain}", cwd="src/salesforce")

# Generate JWT Token
def generate_jwt_token(consumer_key, private_key_path, username, audience):
    print("Generating JWT Token...")
    
    # Load the private key from file
    with open(private_key_path, 'rb') as key_file:
        private_key = serialization.load_pem_private_key(
            key_file.read(),
            password=None,
            backend=default_backend()
        )

    # Define the JWT claims
    current_time = datetime.datetime.utcnow()
    claims = {
        'iss': consumer_key, # Consumer Key
        'sub': username,  # Salesforce Username
        'aud': audience,  # Audience (Salesforce Login URL)
        'exp': current_time + datetime.timedelta(days=30)  # Token expiry (1 month)
    }
    
    # Sign the JWT token using the private key
    token = jwt.encode(claims, private_key, algorithm='RS256')
    
    print("JWT Token generated successfully.")
    return token

# Test JWT Token by making a request to Salesforce
def test_jwt_token(token, login_url):
    print("Testing JWT Token with Salesforce...")

    # Set the headers and payload for the request
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    payload = {
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': token
    }
    
    # Send the POST request to Salesforce Token Endpoint
    response = requests.post(login_url, data=payload, headers=headers)
    
    # Process the response
    if response.status_code == 200:
        print("JWT Token authentication successful!")
        return json.loads(response.text)
    else:
        print(f"Failed to authenticate JWT Token. Status Code: {response.status_code}")
        print(f"Error Response: {response.text}")
        return None

# Create Glue Job
def create_glue_connection(create_glue_connection, role_arn, secret_arn, region): 
    print("Creating Glue Connection...")

    # Construct the Glue Connection command
    connection_input = {
        "ConnectionType": "SALESFORCE",
        "ConnectionProperties": {
            "KAFKA_SSL_ENABLED": "false",
            "INSTANCE_URL": salesforce_domain,
            "ROLE_ARN": f"{role_arn}"
        },
        "AuthenticationConfiguration": {
            "AuthenticationType": "OAUTH2",
            "OAuth2Properties": {
                "OAuth2GrantType": "JWT_BEARER",
                "TokenUrl": "https://login.salesforce.com/services/oauth2/token"
            },
            "SecretArn": secret_arn
        },
        "Name": "salesforce_connection"
    }

    glue_connection_cmd = (
        f"aws glue create-connection "
        f"--region {region} "
        f"--connection-input '{json.dumps(connection_input)}'"
    )

    # Run the Glue Connection command
    run_cli_command(glue_connection_cmd)

# Create Glue Job
def create_glue_jobs(region, role_arn, artifact_bucket):
    print("Creating Glue Visual Job for fetching Salesforce cases...")

    job_command = {
        "Name": "glueetl",
        "ScriptLocation": f"s3://{artifact_bucket}/scripts/fetch_salesforce_cases.py",
        "PythonVersion": "3"
    }

    default_args = {
        "--enable-metrics": "true",
        "--enable-spark-ui": "true",
        "--extra-py-files": "s3://aws-glue-studio-transforms-510798373988-prod-us-east-1/gs_common.py,s3://aws-glue-studio-transforms-510798373988-prod-us-east-1/gs_repartition.py",
        "--spark-event-logs-path": f"s3://{artifact_bucket}/sparkHistoryLogs/",
        "--enable-job-insights": "true",
        "--job-mode": "VISUAL",
        "--enable-observability-metrics": "true",
        "--enable-glue-datacatalog": "true",
        "--enable-continuous-cloudwatch-log": "true",
        "--job-bookmark-option": "job-bookmark-disable",
        "--job-language": "python",
        "--TempDir": f"s3://{artifact_bucket}/temporary/"
    }

    code_gen_nodes = { 
        "node-1728393231363": { "ConnectorDataSource": { "Name": "Salesforce", "ConnectionType": "salesforce", "Data": { "API_VERSION": "v60.0", "connectionName": "salesforce_connection", "ENTITY_NAME": "Case" }, "OutputSchemas": [ { "Columns": [ { "Name": "id", "Type": "string" }, { "Name": "isdeleted", "Type": "boolean" }, { "Name": "masterrecordid", "Type": "null" }, { "Name": "casenumber", "Type": "string" }, { "Name": "contactid", "Type": "string" }, { "Name": "accountid", "Type": "string" }, { "Name": "assetid", "Type": "null" }, { "Name": "sourceid", "Type": "null" }, { "Name": "parentid", "Type": "null" }, { "Name": "suppliedname", "Type": "null" }, { "Name": "suppliedemail", "Type": "null" }, { "Name": "suppliedphone", "Type": "string" }, { "Name": "suppliedcompany", "Type": "null" }, { "Name": "type", "Type": "string" }, { "Name": "status", "Type": "string" }, { "Name": "reason", "Type": "string" }, { "Name": "origin", "Type": "string" }, { "Name": "subject", "Type": "string" }, { "Name": "priority", "Type": "string" }, { "Name": "description", "Type": "string" }, { "Name": "isclosed", "Type": "boolean" }, { "Name": "closeddate", "Type": "timestamp" }, { "Name": "isescalated", "Type": "boolean" }, { "Name": "ownerid", "Type": "string" }, { "Name": "createddate", "Type": "timestamp" }, { "Name": "createdbyid", "Type": "string" }, { "Name": "lastmodifieddate", "Type": "timestamp" }, { "Name": "lastmodifiedbyid", "Type": "string" }, { "Name": "systemmodstamp", "Type": "timestamp" }, { "Name": "contactphone", "Type": "string" }, { "Name": "contactmobile", "Type": "string" }, { "Name": "contactemail", "Type": "string" }, { "Name": "contactfax", "Type": "string" }, { "Name": "comments", "Type": "null" }, { "Name": "lastvieweddate", "Type": "timestamp" }, { "Name": "lastreferenceddate", "Type": "timestamp" }, { "Name": "engineeringreqnumber__c", "Type": "string" }, { "Name": "slaviolation__c", "Type": "string" }, { "Name": "product__c", "Type": "string" }, { "Name": "potentialliability__c", "Type": "string" } ] } ] } }, 
        "node-1728394025646": { "DynamicTransform": { "Name": "Autobalance Processing", "TransformName": "gs_repartition", "Inputs": [ "node-1728393231363" ], "Parameters": [ { "Name": "numPartitionsStr", "Type": "str", "Value": [ "1" ], "IsOptional": True } ], "FunctionName": "gs_repartition", "Path": "s3://aws-glue-studio-transforms-510798373988-prod-us-east-1/gs_repartition.py", "Version": "1.0.0", "OutputSchemas": [ { "Columns": [ { "Name": "Id", "Type": "string" }, { "Name": "IsDeleted", "Type": "boolean" }, { "Name": "MasterRecordId", "Type": "null" }, { "Name": "CaseNumber", "Type": "string" }, { "Name": "ContactId", "Type": "string" }, { "Name": "AccountId", "Type": "string" }, { "Name": "AssetId", "Type": "null" }, { "Name": "SourceId", "Type": "null" }, { "Name": "ParentId", "Type": "null" }, { "Name": "SuppliedName", "Type": "null" }, { "Name": "SuppliedEmail", "Type": "null" }, { "Name": "SuppliedPhone", "Type": "string" }, { "Name": "SuppliedCompany", "Type": "null" }, { "Name": "Type", "Type": "string" }, { "Name": "Status", "Type": "string" }, { "Name": "Reason", "Type": "string" }, { "Name": "Origin", "Type": "string" }, { "Name": "Subject", "Type": "string" }, { "Name": "Priority", "Type": "string" }, { "Name": "Description", "Type": "string" }, { "Name": "IsClosed", "Type": "boolean" }, { "Name": "ClosedDate", "Type": "timestamp" }, { "Name": "IsEscalated", "Type": "boolean" }, { "Name": "OwnerId", "Type": "string" }, { "Name": "CreatedDate", "Type": "timestamp" }, { "Name": "CreatedById", "Type": "string" }, { "Name": "LastModifiedDate", "Type": "timestamp" }, { "Name": "LastModifiedById", "Type": "string" }, { "Name": "SystemModstamp", "Type": "timestamp" }, { "Name": "ContactPhone", "Type": "string" }, { "Name": "ContactMobile", "Type": "string" }, { "Name": "ContactEmail", "Type": "string" }, { "Name": "ContactFax", "Type": "string" }, { "Name": "Comments", "Type": "null" }, { "Name": "LastViewedDate", "Type": "timestamp" }, { "Name": "LastReferencedDate", "Type": "timestamp" }, { "Name": "EngineeringReqNumber__c", "Type": "string" }, { "Name": "SLAViolation__c", "Type": "string" }, { "Name": "Product__c", "Type": "string" }, { "Name": "PotentialLiability__c", "Type": "string" } ] } ] } }, 
        "node-1728393254134": { "S3DirectTarget": { "Name": "Amazon S3", "Inputs": [ "node-1728394025646" ], "PartitionKeys": [], "Path": f"s3://{artifact_bucket}/export/", "Compression": "none", "Format": "json", "SchemaChangePolicy": { "EnableUpdateCatalog": False } } } }

    job_cmd = (
        f"aws glue create-job --name '{STACK_NAME}_fetch_salesforce_cases' "
        f"--role {role_arn} "
        f"--command '{json.dumps(job_command)}' "
        f"--default-arguments '{json.dumps(default_args)}' "
        f"--connections 'Connections=[\"salesforce_connection\"]' "
        f"--worker-type G.1X --number-of-workers 10 --glue-version 4.0 "
        f"--code-gen-configuration-nodes '{json.dumps(code_gen_nodes)}' "
        f"--region {region}"
    )

    run_cli_command(job_cmd)

    print("Creating Glue Visual Job for Bulk Import cases...")
    job_command = {
        "Name": "glueetl",
        "ScriptLocation": f"s3://{artifact_bucket}/scripts/write_salesforce_cases.py",
        "PythonVersion": "3"
    }

    default_args = {
        "--enable-metrics": "true",
        "--enable-spark-ui": "true",
        "--extra-py-files": "s3://aws-glue-studio-transforms-510798373988-prod-us-east-1/gs_common.py,s3://aws-glue-studio-transforms-510798373988-prod-us-east-1/gs_repartition.py",
        "--spark-event-logs-path": f"s3://{artifact_bucket}/sparkHistoryLogs/",
        "--enable-job-insights": "true",
        "--job-mode": "VISUAL",
        "--enable-observability-metrics": "true",
        "--enable-glue-datacatalog": "true",
        "--enable-continuous-cloudwatch-log": "true",
        "--job-bookmark-option": "job-bookmark-disable",
        "--job-language": "python",
        "--TempDir": f"s3://{artifact_bucket}/temporary/"
    }
    code_gen_nodes = {
        "node-1728464194175": { "S3JsonSource": { "Name": "Amazon S3", "Paths": [ f"s3://{artifact_bucket}/cases/support_cases.json" ], "Recurse": False } },
        "node-1728464198609": { "ApplyMapping": { "Name": "Change Schema", "Inputs": [ "node-1728464194175" ], "Mapping": [ {"ToKey": "Origin", "FromPath": ["origin"], "FromType": "string", "ToType": "string"}, {"ToKey": "Description", "FromPath": ["description"], "FromType": "string", "ToType": "string"}, {"ToKey": "Reason", "FromPath": ["reason"], "FromType": "string", "ToType": "string"}, {"ToKey": "Status", "FromPath": ["status"], "FromType": "string", "ToType": "string"}, {"ToKey": "Priority", "FromPath": ["priority"], "FromType": "string", "ToType": "string"}, {"ToKey": "Subject", "FromPath": ["subject"], "FromType": "string", "ToType": "string"}, {"ToKey": "Type", "FromPath": ["type"], "FromType": "string", "ToType": "string"} ] } },
        "node-1728464209327": { "ConnectorDataTarget": { "Name": "Salesforce", "ConnectionType": "salesforce", "Data": { "API_VERSION": "v60.0", "connectionName": "salesforce_connection", "writeOperation": "INSERT", "ENTITY_NAME": "Case" }, "Inputs": [ "node-1728464198609" ] } }
    }

    job_cmd = (
        f"aws glue create-job --name '{STACK_NAME}_write_salesforce_cases' "
        f"--role {role_arn} "
        f"--command '{json.dumps(job_command)}' "
        f"--default-arguments '{json.dumps(default_args)}' "
        f"--connections 'Connections=[\"salesforce_connection\"]' "
        f"--worker-type G.1X --number-of-workers 10 --glue-version 4.0 "
        f"--code-gen-configuration-nodes '{json.dumps(code_gen_nodes)}' "
        f"--region {region}"
    )
    run_cli_command(job_cmd)

# Main Function
def main(salesforce_domain, username, aws_region_id="us-east-1"):
    print("Starting Salesforce Connected App automation process...")
    
    # Clean old files
    clean_up_default_files()

    # Generate PEM Keys
    private_key_path, public_key_path = generate_pem_keys_with_cert()    
    
    # Login to Salesforce Org
    login_to_org(salesforce_domain)
    
    # Fetch Salesforce User ID
    user_id = fetch_salesforce_user_id(username, salesforce_domain)
    
    # Generate Consumer Key and Secret
    consumer_key, consumer_secret = generate_consumer_key_and_secret()
    
    # Create new project
    create_sfdc_project()   

    # Create XML for the Connected App
    connected_app_xml_path = create_connected_app_xml(salesforce_domain, username, user_id, public_key_path, consumer_key, consumer_secret, aws_region_id)

    # Deploy your connected app
    deploy_project(salesforce_domain)
    
    # Generate JWT Token
    salesforce_audience = "https://login.salesforce.com"  # For production, use the appropriate login URL
    jwt_token = generate_jwt_token(consumer_key, private_key_path, username, salesforce_audience)

    # Test JWT Token
    login_url = f"{salesforce_audience}/services/oauth2/token"
    access_token = test_jwt_token(jwt_token, login_url)

    # Output JWT
    print(f"JWT Token: {jwt_token}")
    if access_token: 
        print(f"Access Token: {access_token['access_token']}")
    
    print(f"Private Key Path: {private_key_path}")
    print(f"Public Key Path: {public_key_path}")
    print("===============================================================\n\n")

    # Create S3 bucket for SAM 
    sam_s3 = create_sam_s3_bucket(aws_region_id)

    # Deploy the SAM template and fetch outputs
    print("Deploying SAM template...")
    deploy_sam(salesforce_domain, consumer_key, consumer_secret, jwt_token, private_key_path, public_key_path, aws_region_id, sam_s3)
    
    # Get CloudFormation Outputs
    cfn_output = parse_cfn_outputs(aws_region_id)
    
    #Parse outputs for relevant data.
    artifact_bucket = cfn_output['artifactBucket']
    mwaa_env_bucket = cfn_output['MWAAEnvironmentBucket']
    role_arn = cfn_output['AWSGlueJobRoleArn']
    secret_arn = cfn_output['AWSGlueConnectionSecretArn']
     
    # Copy Airflow DAGs, Glue jobs and certificates to respective S3 buckets
    copy_files_to_s3(artifact_bucket, mwaa_env_bucket)

    # Create a glue job
    create_glue_connection(salesforce_domain, role_arn, secret_arn, aws_region_id)
    
    # Create Glue Visual jobs
    create_glue_jobs(aws_region_id, role_arn, artifact_bucket)

    # Output results
    print("Process completed successfully.")
    print("===============================================================")
    print(f"Salesforce App Consumer Key: {consumer_key}")
    print(f"Salesforce App Consumer Secret: {consumer_secret}")        
    

if __name__ == "__main__":
    check_aws_cli_version()

    if len(sys.argv) != 4:
        print("Usage: python script.py <Salesforce_domain> <Salesforce Username [email]> <AWS Region Id>")
        sys.exit(1)
    
    salesforce_domain = sys.argv[1]
    username = sys.argv[2]
    aws_region_id = sys.argv[3]
    # Check if salesforce_domain starts with http:// or https://, if not prepend https://
    if not salesforce_domain.startswith(('http://', 'https://')):
        salesforce_domain = f"https://{salesforce_domain}"
    
    main(salesforce_domain, username, aws_region_id)