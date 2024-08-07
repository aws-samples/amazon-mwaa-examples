#!/bin/sh

BUCKET_NAME="${BUCKET_NAME:-$MY_BUCKET_NAME}" # prefer environment variable BUCKET_NAME or set MY_BUCKET_NAME to your own
KEY_PAIR="${KEY_PAIR:-$MY_KEY_PAIR}" # prefer environment variable KEY_PAIR or set MY_KEY_PAIR to your own

# Example: BUCKET_NAME=airflow-bucket KEY_PAIR=mykeypair ./deploy.sh

echo "Using S3 bucket: $BUCKET_NAME"
echo "Using key pair: $KEY_PAIR"

aws cloudformation create-stack --stack-name least-privilege-blog --template-body file://template.yaml \
    --parameters ParameterKey=S3Bucket,ParameterValue=$BUCKET_NAME ParameterKey=SSHKeypairName,ParameterValue=$KEY_PAIR\
    --capabilities CAPABILITY_IAM
