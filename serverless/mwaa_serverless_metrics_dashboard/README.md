

### MWAA Serverless Monitoring and observability

This example creates a monitoring dashboard for MWAA Serverless that provides:

- Workflow execution status

- Task-level performance metrics

- Historical success rates

---
*Note:* Throughout this post, we use example values that you'll need to replace with your own:
- Replace `amzn-s3-demo-bucket` with your S3 bucket name
- Replace `111122223333` with your AWS account ID
- Replace `us-east-2` with your AWS Region. MWAA Serverless is available in multiple AWS Regions. Check the [List of AWS Services Available by Region](https://aws.amazon.com/about-aws/global-infrastructure/regional-product-services/) for current availability.

---

1. You start by creating the Lambda function that will provide information
for our CloudWatch dashboard. This function processes workflow execution
data and generates CloudWatch metrics:

[mwaa_serverless_metrics_lambda.py](mwaa_serverless_metrics_lambda.py)

2. You will need an IAM role that can call the MWAA Serverless functions
for the Lambda.
  
```bash
aws iam create-role \
    --role-name lambda-mwaa-serverless-execution-role \
    --assume-role-policy-document '{
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "lambda.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }' \
    --region us-east-2

aws iam put-role-policy \
    --role-name lambda-mwaa-serverless-execution-role \
    --policy-name lambda-mwaa-serverless-execution-policy \
    --region us-east-2 \
    --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "airflow-serverless:List*",
                "airflow-serverless:Get*"
            ],
            "Resource": "*" 
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:CreateTable",
                "dynamodb:DescribeTable"
            ],
            "Resource": "arn:aws:dynamodb:*:*:table/mwaa-metrics-state"
        },
        {
            "Effect": "Allow",
            "Action": [
                "cloudwatch:PutMetricData"
            ],
            "Resource": "*",
            "Condition": {
                "StringEquals": {
                    "cloudwatch:namespace": "MWAA/Serverless"
                }
            }
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:log-group:/aws/mwaa-serverless/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/*"
        }
    ]
}'
```

3. You will need to use the latest boto3 libraries with our Lambda, which
will be added via a requirements file:

```bash
mkdir mwaa-metrics-lambda-package
pip install "boto3>=1.40.75" -t  mwaa-metrics-lambda-package/
cp mwaa_serverless_metrics_lambda.py  mwaa-metrics-lambda-package/
cd mwaa-metrics-lambda-package && zip -r ../mwaa-metrics-lambda-package.zip . && cd ..
```

4. Finally, you can deploy the Lambda function.

```bash
aws lambda create-function \
    --function-name mwaa_serverless_metrics_lambda \
    --runtime python3.12 \
    --role arn:aws:iam::111122223333:role/lambda-execution-role \
    --handler mwaa_serverless_metrics_lambda.lambda_handler \
    --zip-file fileb://mwaa-metrics-lambda-package.zip \
    --timeout 300 \
    --memory-size 128 \
    --region us-east-2
```

5. You will also need an EventBridge rule with necessary permissions in
order to update the metrics:

```bash
# Create EventBridge rule for every 5 minutes
aws events put-rule \
  --name "mwaa-metrics-lambda-schedule" \
  --schedule-expression "rate(5 minutes)" \
  --region us-east-2

# Add permission for EventBridge to invoke Lambda
aws lambda add-permission \
  --function-name mwaa-metrics-lambda \
  --statement-id "mwaa-metrics-lambda-eventbridge" \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:us-east-2:111122223333:rule/mwaa-metrics-lambda-schedule" \
  --region us-east-2 \
  2>/dev/null || true

# Add Lambda as target to EventBridge rule
aws events put-targets \
  --rule "mwaa-metrics-lambda-schedule" \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-2:111122223333:function:mwaa-metrics-lambda" \
  --region us-east-2
```

6. You will then create the dashboard code:

[mwaa_serverless_metrics_dashboard.json](mwaa_serverless_metrics_dashboard.json)

7. You then publish the dashboard:

```bash
aws cloudwatch put-dashboard \
  --dashboard-name "MWAA-Serverless-Metrics-Dashboard" \
  --dashboard-body file://mwaa_serverless_metrics_dashboard.json \
  --region us-east-2
```

---
#### Clean up resources


To avoid incurring ongoing charges, follow these steps to clean up all
resources created during this example:

1.  Remove the Lambda function:

```bash
aws lambda delete-function --function-name mwaa-metrics-lambda
```

2.  Remove the CloudWatch dashboard:

```bash
aws cloudwatch delete-dashboards --dashboard-names MWAA-Serverless-Dashboard
```


3.  Remove the IAM roles and policies created for this tutorial:

```bash
aws iam delete-role-policy --role-name lambda-mwaa-serverless-execution-role --policy-name lambda-mwaa-serverless-execution-policy 
aws iam delete-role --role-name lambda-mwaa-serverless-execution-role
```

If you encounter any errors during cleanup, ensure you have the
necessary permissions and that resources exist before attempting to
delete them. Some resources may have dependencies that require them to
be deleted in a specific order.
