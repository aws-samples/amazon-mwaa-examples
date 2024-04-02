import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { ExternalStack } from "../lib/external-stack";
import { MwaaStack } from "../lib/mwaa-stack";
import { VpcStack } from "../lib/vpc-stack";

describe("Execution unit tests for dev account", () => {
  // Generate Storage stack
  const stageName = "dev";
  const sampleNumber = "111111111111";
  const sampleID = "12345678-54de-4f0c-be44-43302a28ef9e";
  const mockApp = new App();
  const vpcStack = new VpcStack(mockApp, "unittest-vpc", {
    stage: stageName,
    subnet_size: 24,
    vpc_cidr: "10.0.0.0/8",
  });
  const mwaaStack = new MwaaStack(mockApp, "unittest-mwaa", {
    dagBucketArn: "fake-s3-arn",
    dagBucketKmsKeyArn: "fake-s3-arn",
    mwaaEnvironmentName: `${stageName}-mwaa-cluster`,
    mwaaPrivateSubnetIds: vpcStack.mwaaPrivateSubnetIds,
    mwaaSecurityGroupIds: [vpcStack.mwaaSecurityGroup.securityGroupId],
    stage: stageName,
  });
  const externalStack = new ExternalStack(mockApp, "unittest-external", {
    albSecurityGroup: vpcStack.albSecurityGroup,
    certificateArn: `arn:aws:acm:eu-west-1:${sampleNumber}:certificate/${sampleID}`,
    lambdaSecurityGroup: vpcStack.lambdaSecurityGroup,
    mwaaEnvironment: mwaaStack.mwaaEnvironment,
    mwaaSecurityGroupIds: [vpcStack.mwaaSecurityGroup.securityGroupId],
    mwaaVpc: vpcStack.mwaaVpc,
    stage: stageName,
  });

  const template = Template.fromStack(externalStack);

  // Execute tests for to confirm setup
  test("Check lambda function", () => {
    // Test preparation
    // Test execution
    template.hasResourceProperties("AWS::Lambda::Function", {
      MemorySize: 512,
      Runtime: "nodejs18.x",
    });
  });

  test("Check ELB settings", () => {
    // Test preparation
    // Test execution
    template.hasResourceProperties(
      "AWS::ElasticLoadBalancingV2::LoadBalancer",
      {
        IpAddressType: "ipv4",
      },
    );
  });

  test("Check ELB target group for MWAA", () => {
    // Test preparation
    // Test execution
    template.hasResourceProperties("AWS::ElasticLoadBalancingV2::TargetGroup", {
      HealthCheckPath: "/health",
      Port: 443,
      Protocol: "HTTPS",
    });
  });

  // Summary check
  test("Check lambda function number", () => {
    // Test preparation
    const expectedValue = 2;
    // Test execution
    template.resourceCountIs("AWS::Lambda::Function", expectedValue);
  });
});
