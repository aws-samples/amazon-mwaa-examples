import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { VpcStack } from "../lib/vpc-stack";

// Generate Storage stack
const stageName = "alpha";
const mockApp = new App();
const stack = new VpcStack(mockApp, "unittest-vpc", {
  stage: stageName,
  subnet_size: 24,
  vpc_cidr: "10.0.0.0/8",
});
const template = Template.fromStack(stack);

// Execute tests for to confirm setup
test("There are four subnets", () => {
  // Test preparation
  const expectedNumber = 4;
  // Test execution
  template.resourceCountIs("AWS::EC2::Subnet", expectedNumber);
});

test("There are two NAT gateways", () => {
  // Test preparation
  const expectedNumber = 2;
  // Test execution
  template.resourceCountIs("AWS::EC2::NatGateway", expectedNumber);
});

test("Check if the VPC has S3 endpoint gateway", () => {
  template.hasResourceProperties("AWS::EC2::VPCEndpoint", {
    VpcEndpointType: "Gateway",
  });
});
