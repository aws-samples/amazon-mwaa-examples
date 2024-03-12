#!/usr/bin/env node
import "source-map-support/register";
import { App, Aspects } from "aws-cdk-lib";
import { AwsSolutionsChecks } from "cdk-nag";
import { ExternalStack } from "./external-stack";
import { MwaaStack } from "./mwaa-stack";
import { StorageStack } from "./storage-stack";
import { VpcStack } from "./vpc-stack";
import { exit } from "process";

const app = new App();
const deployment: string = process.env.DEPLOYMENT ?? "dev";
const certArn: string = process.env.CERTIFICATE_ARN ?? "not found";
if (certArn === "not found") {
  console.log("Follow instructions how to generate and upload SSL certificate");
  exit();
} else {
  console.log(`Found following cert ARN: ${certArn}`);
}

const vpcStack = new VpcStack(app, `${deployment}-vpc`, {
  description: "VPC items for MWAA",
  stage: deployment,
  subnet_size: 24,
  vpc_cidr: "10.20.0.0/16",
});
const storageStack = new StorageStack(app, `${deployment}-storage`, {
  description: "Storage items for MWAA",
  stage: deployment,
});

const mwaaStack = new MwaaStack(app, `${deployment}-mwaa`, {
  description: "Main MWAA cluster",
  dagBucketArn: storageStack.dagBucket.bucketArn,
  dagBucketKmsKeyArn: storageStack.dagBucketKmsKey.keyArn,
  mwaaEnvironmentName: `${deployment}-mwaa-cluster`,
  mwaaPrivateSubnetIds: vpcStack.mwaaPrivateSubnetIds,
  mwaaSecurityGroupIds: [vpcStack.mwaaSecurityGroup.securityGroupId],
  stage: deployment,
});

const externalStack = new ExternalStack(app, `${deployment}-external`, {
  description: "Items for external access and authentication",
  albSecurityGroup: vpcStack.albSecurityGroup,
  certificateArn: certArn,
  lambdaSecurityGroup: vpcStack.lambdaSecurityGroup,
  mwaaEnvironment: mwaaStack.mwaaEnvironment,
  mwaaSecurityGroupIds: [vpcStack.mwaaSecurityGroup.securityGroupId],
  mwaaVpc: vpcStack.mwaaVpc,
  stage: deployment,
});

// Add security check for all items in the app
Aspects.of(vpcStack).add(new AwsSolutionsChecks());
Aspects.of(storageStack).add(new AwsSolutionsChecks());
Aspects.of(mwaaStack).add(new AwsSolutionsChecks());
Aspects.of(externalStack).add(new AwsSolutionsChecks());
