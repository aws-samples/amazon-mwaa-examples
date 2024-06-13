# Airflow sample image processing pipeline with Airflow 2.0.2

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

### 1. Create S3 Bucket and upload DAG, requirements.txt, and images

```sh
./setup.sh <bucket name>
```

Note down the version number from the last command. This will be used during next step.

### 2. Deploy the SAM template

```sh
sam build
sam deploy --stack-name MWAA-image-processing -g
```

## Access Airflow UI

- Access Airflow UI. The webserver URL will be in the output of the cloudformation template

- Trigger the Dag using the JSON given below

```json
{
  "s3Bucket":"{bucket_name}",
  "s3Key":"images/1_happy_face.jpg",
  "RekognitionCollectionId":"image_processing",
  "userId": "userId"
}
```

## Useful CLI commands while testing

```sh
aws rekognition list-faces --collection-id image_processing

aws rekognition delete-faces --collection-id image_processing --face-ids '["faceid"]'
```
