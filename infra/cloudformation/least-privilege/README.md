# Least Privilege Environments in MWAA for VPC Resources

Blog companion code

## Getting Started

### Prerequisites

First, ensure that you have installed the following tools locally.

1. [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
2. [MWAA deployer permissions](https://docs.aws.amazon.com/mwaa/latest/userguide/access-policies.html#full-access-policy)

### Deployment Steps

To create private MWAA environment with no NAT/IGW but with VPCEndpoints, run the command below after replacing `your_bucket_name` with the S3 Bucket where DAGs are present:

```sh
aws cloudformation create-stack --stack-name mwaa-environment-private-network --template-body file://template.yaml --parameters ParameterKey=S3Bucket,ParameterValue=your_bucket_name --capabilities CAPABILITY_IAM

```

Note the values of the stack output. You'll need these for the following steps.

## SSH tunnel to Airflow UI

```sh
ssh -i mykeypair.pem -N -D 8157 ec2-user@YOUR_PUBLIC_IPV4
```

- `-N`: Tells SSH that no remote command needs to be executed.
- `-D`: This sets up a SOCKS proxy on the specified local port.

This will create an SSH tunnel that sets up a SOCKS proxy on your local port 8157, using your EC2 instance as an intermediary.

Now that is running, time to configure your browser. If you are NOT using a browser plugin (like FoxyProxy) then many web browsers allow you to configure proxies via a command line or configuration parameter. For example, with Chromium you can start the browser with the following command:

`chromium --proxy-server="socks5://localhost:8157"`

Which will start a browser session which will now use the ssh tunnel to proxy its requests. If you open your Private MWAA url as follows:

`https://{unique-id}-vpce.{region}.airflow.amazonaws.com/home`

(Remember, you will have to add the https:// first as well as append /home from the uri you see in the MWAA console)

All traffic from these applications will be routed through the SSH tunnel and your EC2 instance, effectively using your EC2 instance as a proxy server.

Remember to replace `mykeypair.pem` with the actual path to your AWS key pair file, and `YOUR_PUBLIC_IPV4` with the DNS name or IP address of your EC2 instance.

You can get the values for `YOUR_PUBLIC_IPV4` and `YOUR_VPC_ENDPOINT_ID` from the Cloudformation stack output.

### Cleanup

```sh
aws cloudformation delete-stack --stack-name mwaa-environment-private-network 
```
