#!/usr/bin/env bash

set -e

S3_BUCKET=$1

die() {
  echo >&2 "$@"
  exit 1
}

[ "$#" -eq 1 ] || die "Usage: setup.sh <bucket>"

if aws s3 ls "s3://$S3_BUCKET" 2>&1 | grep -q 'NoSuchBucket'; then
  echo "Creating S3 bucket: $S3_BUCKET"
  aws s3api create-bucket --bucket $S3_BUCKET
else
  echo "S3 bucket already exists: $S3_BUCKET"
fi
aws s3api put-bucket-versioning --bucket $S3_BUCKET --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket $S3_BUCKET --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "Copying files to S3"
aws s3 cp ./dags/2.0/image_processing.py s3://$S3_BUCKET/dags/image-processing.py
aws s3 cp images s3://$S3_BUCKET/images --recursive

echo "Uploading requirements.txt"
VERSION=$(aws s3api put-object --bucket $S3_BUCKET --key requirements.txt --body dags/2.0/requirements.txt --query 'VersionId' --output text)
echo "requirements.txt VersionId: $VERSION"
