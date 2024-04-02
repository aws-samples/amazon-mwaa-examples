import { CfnOutput, StackProps, Stack } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import * as mwaa from "aws-cdk-lib/aws-mwaa";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";

interface DeploymentStackProps extends StackProps {
  readonly stage: string;
  readonly mwaaEnvironmentName: string;
  readonly mwaaPrivateSubnetIds: string[];
  readonly mwaaSecurityGroupIds: string[];
  readonly dagBucketArn: string;
  readonly dagBucketKmsKeyArn: string;
}

export class MwaaStack extends Stack {
  // Export value
  public readonly mwaaEnvironment: mwaa.CfnEnvironment;

  constructor(
    scope: Construct,
    id: string,
    readonly props: DeploymentStackProps,
  ) {
    super(scope, id, props);
    // Local configuration
    const MWAA_VERSION = "2.7.2";
    const MWAA_SIZE = "mw1.small";

    // Main MWAA Stack
    // IAM policy and role for MWAA services
    const mwaaPolicyDocument = new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          actions: ["airflow:PublishMetrics"],
          resources: [
            `arn:aws:airflow:${this.region}:${this.account}:environment/*`,
          ],
        }),
        new iam.PolicyStatement({
          actions: ["s3:GetObject*", "s3:GetBucket*", "s3:List*"],
          resources: [
            `${this.props.dagBucketArn}`,
            `${this.props.dagBucketArn}/*`,
          ],
        }),
        new iam.PolicyStatement({
          actions: [
            "logs:CreateLogGroup",
            "logs:CreateLogStream",
            "logs:GetLogEvents",
            "logs:GetLogRecord",
            "logs:GetLogGroupFields",
            "logs:GetQueryResults",
            "logs:PutLogEvents",
          ],
          resources: [
            `arn:aws:logs:${this.region}:${this.account}:log-group:*`,
          ],
        }),
        new iam.PolicyStatement({
          actions: ["cloudwatch:PutMetricData", "logs:DescribeLogGroups"],
          resources: ["*"],
        }),
        new iam.PolicyStatement({
          actions: [
            "sqs:ChangeMessageVisibility",
            "sqs:GetQueueAttributes",
            "sqs:DeleteMessage",
            "sqs:GetQueueUrl",
            "sqs:ReceiveMessage",
            "sqs:SendMessage",
          ],
          resources: [`arn:aws:sqs:${this.region}:*:*`],
        }),
        new iam.PolicyStatement({
          actions: [
            "kms:Decrypt",
            "kms:DescribeKey",
            "kms:GenerateDataKey*",
            "kms:Encrypt",
            "kms:ReEncrypt*",
          ],
          resources: ["arn:aws:kms:*:*:key/*"],
        }),
      ],
    });
    const mwaaRole = new iam.Role(this, "MWAAExecutionRole", {
      assumedBy: new iam.CompositePrincipal(
        new iam.ServicePrincipal("airflow.amazonaws.com"),
        new iam.ServicePrincipal("airflow-env.amazonaws.com"),
      ),
      // custom description if desired
      description: "This is an execution role for MWAA services",
      inlinePolicies: { mwaa_policy: mwaaPolicyDocument },
    });

    // MWAA configuration
    // Logging configuration setup
    const mwaaLoggingConfigurationProperty: mwaa.CfnEnvironment.LoggingConfigurationProperty =
      {
        taskLogs: {
          enabled: true,
          logLevel: "INFO",
        },
        webserverLogs: {
          enabled: true,
          logLevel: "INFO",
        },
      };
    // Network configuration setup
    const mwaaNetworkConfigurationProperty: mwaa.CfnEnvironment.NetworkConfigurationProperty =
      {
        securityGroupIds: this.props.mwaaSecurityGroupIds,
        subnetIds: this.props.mwaaPrivateSubnetIds,
      };
    // MWAA cluster
    this.mwaaEnvironment = new mwaa.CfnEnvironment(this, "MWAA", {
      name: this.props.mwaaEnvironmentName,
      // Optional parameters
      airflowVersion: MWAA_VERSION,
      dagS3Path: "dags/",
      environmentClass: MWAA_SIZE,
      executionRoleArn: mwaaRole.roleArn,
      kmsKey: this.props.dagBucketKmsKeyArn,
      loggingConfiguration: mwaaLoggingConfigurationProperty,
      networkConfiguration: mwaaNetworkConfigurationProperty,
      sourceBucketArn: this.props.dagBucketArn,
      webserverAccessMode: "PRIVATE_ONLY",
    });

    // Stack Outputs
    new CfnOutput(this, "MWAARoleARN", {
      description: "MWAA role ARN",
      value: mwaaRole.roleArn,
    });
    new CfnOutput(this, "MWAAInternalUrl", {
      description: "MWAA internal access url",
      value: `https://${this.mwaaEnvironment.attrWebserverUrl}`,
    });

    // CDK NAG suppressions
    NagSuppressions.addResourceSuppressions(
      mwaaRole,
      [
        {
          id: "AwsSolutions-IAM5",
          reason: "False positive, the CDK generate this policies with *",
        },
      ],
      false,
    );
  }
}
