import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { MwaaStack } from "../lib/mwaa-stack";

describe("Execution unit tests for dev account", () => {
  // Generate Storage stack
  const stageName = "dev";
  const mockApp = new App();
  const stack = new MwaaStack(mockApp, "unittest-mwaa", {
    description: "Main MWAA cluster",
    dagBucketArn: "fake-s3-arn",
    dagBucketKmsKeyArn: "fake-s3-arn",
    mwaaEnvironmentName: `${stageName}-mwaa-cluster`,
    mwaaPrivateSubnetIds: ["fake-subnet-id1", "fake-subnet-id2"],
    mwaaSecurityGroupIds: ["fake-sg-id1"],
    stage: stageName,
  });

  const template = Template.fromStack(stack);

  // Execute tests for to confirm setup
  test("There is one role in the stack", () => {
    // Test preparation
    const expectedNumber = 1;
    // Test execution
    template.resourceCountIs("AWS::IAM::Role", expectedNumber);
  });

  test("MWAA configuration setup", () => {
    // Test execution
    template.hasResourceProperties("AWS::MWAA::Environment", {
      DagS3Path: "dags/",
    });
  });
});
