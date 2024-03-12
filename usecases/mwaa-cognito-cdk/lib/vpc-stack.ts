import { CfnOutput, StackProps, Stack } from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import { Construct } from "constructs";
import { NagSuppressions } from "cdk-nag";

interface DeploymentStackProps extends StackProps {
  readonly stage: string;
  readonly subnet_size: number;
  readonly vpc_cidr: string;
}

export class VpcStack extends Stack {
  // Export values
  public readonly albSecurityGroup: ec2.SecurityGroup;
  public readonly lambdaSecurityGroup: ec2.SecurityGroup;
  public readonly mwaaSecurityGroup: ec2.SecurityGroup;
  public readonly mwaaPrivateSubnetIds: string[] = [];
  public readonly mwaaVpc: ec2.Vpc;

  constructor(
    scope: Construct,
    id: string,
    readonly props: DeploymentStackProps,
  ) {
    super(scope, id, props);

    // Main VPC Stack
    this.mwaaVpc = new ec2.Vpc(this, "MWAAVpc", {
      // Add S3 endpoint for data transfer
      gatewayEndpoints: {
        S3: {
          service: ec2.GatewayVpcEndpointAwsService.S3,
        },
      },
      // CIDR and 2 AZs
      ipAddresses: ec2.IpAddresses.cidr(this.props.vpc_cidr),
      maxAzs: 2,
      // Subnet configuration
      subnetConfiguration: [
        {
          cidrMask: this.props.subnet_size,
          name: "private",
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        },
        {
          cidrMask: this.props.subnet_size,
          name: "public",
          subnetType: ec2.SubnetType.PUBLIC,
        },
      ],
    });
    this.mwaaVpc.addFlowLog("MWAAFlowLogCloudWatch", {
      trafficType: ec2.FlowLogTrafficType.REJECT,
      maxAggregationInterval: ec2.FlowLogMaxAggregationInterval.ONE_MINUTE,
    });
    // MWAA Security Group with all traffic allow
    this.mwaaSecurityGroup = new ec2.SecurityGroup(this, "MWAASecurityGroup", {
      allowAllOutbound: true,
      description: "MWAA Internal Security Group",
      vpc: this.mwaaVpc,
    });
    this.mwaaSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(this.props.vpc_cidr),
      ec2.Port.allTraffic(),
    );
    // Lambda Security Group with internal traffic allow
    this.lambdaSecurityGroup = new ec2.SecurityGroup(
      this,
      "LambdaSecurityGroup",
      {
        description: "Lambda Internal Security Group",
        vpc: this.mwaaVpc,
      },
    );
    this.lambdaSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(this.props.vpc_cidr),
      ec2.Port.allTcp(),
    );
    // ALB Security group with HTTP and HTTPS allow
    this.albSecurityGroup = new ec2.SecurityGroup(this, "ALBSecurityGroup", {
      description: "ALB External Security Group",
      vpc: this.mwaaVpc,
    });
    this.albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      "Allow HTTPS",
    );
    this.albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      "Allow HTTP",
    );
    // Collect pvitate subnets into the array
    for (const subnet of this.mwaaVpc.privateSubnets) {
      this.mwaaPrivateSubnetIds.push(subnet.subnetId);
    }
    // Stack Outputs
    new CfnOutput(this, "VPCId", {
      description: "MWAA VPC Id",
      value: this.mwaaVpc.vpcId,
    });
    new CfnOutput(this, "MWAASecurityGroupIds", {
      description: "MWAA Security Group Ids",
      value: this.mwaaSecurityGroup.securityGroupId,
    });
    new CfnOutput(this, "MWAAPrivateSubnetIds", {
      description: "MWAA Private Subnets Ids",
      value: this.mwaaPrivateSubnetIds.join(" ,"),
    });

    // CDK NAG suppressions
    NagSuppressions.addResourceSuppressions(
      this.albSecurityGroup,
      [
        {
          id: "AwsSolutions-EC23",
          reason: "False positive, this is an item for external ALB",
        },
      ],
      false,
    );
  }
}
