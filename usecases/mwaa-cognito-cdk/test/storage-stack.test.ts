import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { StorageStack } from "../lib/storage-stack";

describe("Execution unit tests for dev account", () => {
  // Generate Storage stack
  const stageName = "dev";
  const mockApp = new App();
  const stack = new StorageStack(mockApp, "unittest-storage", {
    stage: stageName,
  });
  const template = Template.fromStack(stack);

  // Execute tests for to confirm setup
  test("There are two S3 buckets in the stack", () => {
    // Test preparation
    const expectedNumber = 2;
    // Test execution
    template.resourceCountIs("AWS::S3::Bucket", expectedNumber);
  });

  test("Check the buckets public access is disabled", () => {
    // Check all objects are disabled for public access
    template.hasResourceProperties("AWS::S3::Bucket", {
      PublicAccessBlockConfiguration: Match.objectEquals({
        BlockPublicAcls: true,
        BlockPublicPolicy: true,
        IgnorePublicAcls: true,
        RestrictPublicBuckets: true,
      }),
    });
  });

  test("Check the buckets have SSE enabled", () => {
    // Check all objects are disabled for public access
    template.hasResourceProperties("AWS::S3::Bucket", {
      BucketEncryption: Match.objectLike({
        ServerSideEncryptionConfiguration: [
          {
            ServerSideEncryptionByDefault: { SSEAlgorithm: "AES256" },
          },
        ],
      }),
    });
  });

  test("Check deployment is properly setup", () => {
    template.hasResourceProperties("Custom::CDKBucketDeployment", {
      DestinationBucketKeyPrefix: "dags",
      Prune: true,
    });
  });
});
