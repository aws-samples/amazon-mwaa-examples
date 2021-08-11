## Airflow sample image processing pipeline with Airflow 1.10.12

This is an Ariflow verion of image processing workflow in [workshop](https://image-processing.serverlessworkshops.io/)

## AWS Services Used

- [Amazon Rekognition](https://aws.amazon.com/rekognition/) for image processing
- [AWS Lambda](https://aws.amazon.com/lambda/) for creating Thumbnails
- [Amazon S3](https://aws.amazon.com/s3/)  for storing/retrieving images
- [Amazon DynamoDB](https://aws.amazon.com/dynamodb/) for storing the metadata

## Workflow
1. Verify the photo shows a clear face.
2. Match against the collection of previously indexed faces
3. Resize the photo to thumbnails to display on the app.
4. Index the user’s face into the collection so it can be used for matching in the future.
5. Store the photo metadata with the user’s profile.

<p align="center">
  <img src="graphview.png" alt="Graphical representation"/>
</p>

## How to Deploy

### 1. Create Rekognition collections
``` 
aws rekognition create-collection --collection-id image_processing
```
### 2. Create S3 Bucket to store Dags, Requirement.txt and plugins. 
```
aws s3api create-bucket --bucket {bucket_name} --region {region}
aws s3api put-bucket-versioning --bucket {bucket_name} --versioning-configuration Status=Enabled

aws s3api put-public-access-block --bucket {bucket_name} --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

```
### 3. Copy requirements to S3
```
aws s3api put-object --bucket {bucket_name} --key requirements.txt --body dags/2.0/requirements.txt --output text
```

Note down the version number from the last command. This will be used during next step.

### 4. Deploy the SAM template
```
sam build
sam deploy --stack-name MWAA-image-processing -g

```

### 5. Copy dag and images

Replace TABLE_NAME with Stack Output.DynamoDBTableName and LAMBDA_FN_NAME with Stack Output.LambdaFunctionName in dags/image-processing.py. Copy the dag and images(to be tested) to the S3 Bucket created in Step 2

```
aws s3 cp dags/2.0/image_processing.py s3://{bucket_name}/dags/image-processing.py

aws s3 cp images s3://{bucket_name}/images --recursive

```

## Access Airflow UI

- Access Airflow UI. The webserver URL will be in the output of the cloudformation template

- Trigger the Dag using the JSON given below

```
{
"s3Bucket":"{bucket_name}",
"s3Key":"images/1_happy_face.jpg",
"RekognitionCollectionId":"image_processing",
"userId": "userId"
}
```

## Useful cli commands while testing
```
aws rekognition list-faces    --collection-id image_processing

aws rekognition delete-faces \
   --collection-id image_processing \
   --face-ids REPLACE_WITH_FACE_ID \
```

<!-- aws s3 cp requirement.txt s3://{bucket_name}/requirement.txt -->


