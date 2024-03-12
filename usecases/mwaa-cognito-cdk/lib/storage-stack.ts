import {
  CfnOutput,
  StackProps,
  Stack,
  Duration,
  RemovalPolicy,
  Size,
} from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import * as kms from "aws-cdk-lib/aws-kms";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";

interface DeploymentStackProps extends StackProps {
  readonly stage: string;
}

export class StorageStack extends Stack {
  // Export values
  public readonly dagBucket: s3.Bucket;
  public readonly dagBucketKmsKey: kms.Key;
  public readonly logsBucket: s3.Bucket;

  constructor(
    scope: Construct,
    id: string,
    readonly props: DeploymentStackProps,
  ) {
    super(scope, id, props);
    // Local configuration
    const LOGS_RETENTION_DAYS = 180;
    const REMOVAL_POLICY = RemovalPolicy.RETAIN;

    // Logging bucket for events
    this.logsBucket = new s3.Bucket(this, "logs-bucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      lifecycleRules: [
        {
          expiration: Duration.days(LOGS_RETENTION_DAYS),
        },
      ],
      objectOwnership: s3.ObjectOwnership.OBJECT_WRITER,
      removalPolicy: REMOVAL_POLICY,
    });

    this.logsBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        actions: ["s3:PutObject"],
        principals: [new iam.ServicePrincipal("logging.s3.amazonaws.com")],
        resources: [`${this.logsBucket.bucketArn}/*`],
      }),
    );
    // Create a KMS key for encryption
    this.dagBucketKmsKey = new kms.Key(this, "dagBucketKmsKey", {
      description: "DAG bucket key for encryption",
      enableKeyRotation: true,
    });
    this.dagBucketKmsKey.addToResourcePolicy(
      new iam.PolicyStatement({
        actions: [
          "kms:Decrypt*",
          "kms:Describe*",
          "kms:GenerateDataKey*",
          "kms:Encrypt*",
          "kms:ReEncrypt*",
        ],
        resources: ["*"],
        principals: [
          new iam.ServicePrincipal(`logs.${this.region}.amazonaws.com`),
        ],
      }),
    );
    // Default bucket for solution
    this.dagBucket = new s3.Bucket(this, "dag-bucket", {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      bucketKeyEnabled: true,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: this.dagBucketKmsKey,
      enforceSSL: true,
      removalPolicy: REMOVAL_POLICY,
      serverAccessLogsBucket: this.logsBucket,
      serverAccessLogsPrefix: `dag/`,
    });

    // Upload files from the ./dags folder
    new s3deploy.BucketDeployment(this, "dagsUpload", {
      destinationBucket: this.dagBucket,
      destinationKeyPrefix: "dags",
      sources: [s3deploy.Source.asset("./dags")],
      memoryLimit: 1024,
      ephemeralStorageSize: Size.mebibytes(10240),
    });

    // Stack Outputs
    new CfnOutput(this, "LogsBucketName", {
      description: "S3 bucket for logs",
      value: this.logsBucket.bucketName,
    });
    new CfnOutput(this, "DagBucketName", {
      description: "S3 bucket for DAG files",
      value: this.dagBucket.bucketName,
    });
    new CfnOutput(this, "DagBucketKmsKeyARN", {
      description: "S3 bucket KMS Key ARN",
      value: this.dagBucketKmsKey.keyArn,
    });

    // CDK NAG suppressions
    NagSuppressions.addStackSuppressions(
      this,
      [
        {
          id: "AwsSolutions-IAM5",
          reason: "False positive, the CDK generate this policies with *",
        },
        {
          id: "AwsSolutions-IAM4",
          reason:
            "False positive, the CDK adds manage role for s3deploy lambda",
          appliesTo: [
            "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
          ],
        },
        {
          id: "AwsSolutions-L1",
          reason:
            "False positive, the CDK generate this lambda function for deploy",
        },
      ],
      false,
    );
    NagSuppressions.addResourceSuppressions(
      this.logsBucket,
      [
        {
          id: "AwsSolutions-S1",
          reason: "False positive, it is logging bucket.",
        },
      ],
      false,
    );
  }
}
