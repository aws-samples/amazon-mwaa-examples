import {
  CfnOutput,
  custom_resources,
  Duration,
  RemovalPolicy,
  StackProps,
  Stack,
} from "aws-cdk-lib";
import * as acm from "aws-cdk-lib/aws-certificatemanager";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as elb from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as elb_actions from "aws-cdk-lib/aws-elasticloadbalancingv2-actions";
import * as elb_targets from "aws-cdk-lib/aws-elasticloadbalancingv2-targets";
import * as iam from "aws-cdk-lib/aws-iam";
import { Runtime } from "aws-cdk-lib/aws-lambda";
import { NodejsFunction } from "aws-cdk-lib/aws-lambda-nodejs";
import * as mwaa from "aws-cdk-lib/aws-mwaa";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import * as path from "path";

interface DepStackProps extends StackProps {
  readonly albSecurityGroup: ec2.SecurityGroup;
  readonly certificateArn: string;
  readonly lambdaSecurityGroup: ec2.SecurityGroup;
  readonly mwaaEnvironment: mwaa.CfnEnvironment;
  readonly mwaaSecurityGroupIds: string[];
  readonly mwaaVpc: ec2.Vpc;
  readonly stage: string;
}

export class ExternalStack extends Stack {
  constructor(
    scope: Construct,
    id: string,
    readonly props: DepStackProps,
  ) {
    super(scope, id, props);

    // User Pool
    const userPool = new cognito.UserPool(this, "UserPool", {
      removalPolicy: RemovalPolicy.DESTROY,
      signInAliases: {
        email: true,
        username: true,
      },
      passwordPolicy: {
        minLength: 8,
      },
      selfSignUpEnabled: false,
    });

    // Cognito Domain for user pool
    const userPoolDomain = new cognito.UserPoolDomain(this, "UserPoolDomain", {
      cognitoDomain: {
        domainPrefix: `mwaa${this.account}`,
      },
      userPool: userPool,
    });

    // Lambda role for auth process
    // Set static to Admin, change in future
    const authRole = new iam.Role(this, "LambdaAuthRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      inlinePolicies: {
        LambdaAuthAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: ["airflow:CreateWebLoginToken"],
              resources: [
                // The last '/Admin' assume MWAA Admin role. For other roles, create more IAM Roles
                `arn:aws:airflow:${this.region}:${this.account}:role/${this.props.mwaaEnvironment.name}/Admin`,
              ],
            }),
          ],
        }),
      },
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole",
        ),
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaVPCAccessExecutionRole",
        ),
      ],
    });

    const authFunction = new NodejsFunction(this, "AuthFunction", {
      entry: path.join(__dirname, "lambdas/auth/index.ts"),
      environment: {
        MWAA_ENDPOINT: this.props.mwaaEnvironment.attrWebserverUrl,
        MWAA_NAME: this.props.mwaaEnvironment.name,
        MWAA_REGION: this.region,
      },
      handler: "handler",
      memorySize: 512,
      role: authRole,
      runtime: Runtime.NODEJS_18_X,
      securityGroups: [this.props.lambdaSecurityGroup],
      timeout: Duration.seconds(30),
      vpc: this.props.mwaaVpc,
    });

    // Application Load Balancer instance
    /**
     * There is a bug with DNS name from ALB https://github.com/aws/aws-cdk/issues/26103
     * Having that you need to make all characters in the callback URLs in the Cognito app lower case.
     * Unfortunately, there is not good options to do so, as in the CFN we only get tocken for it.
     * To address it there is the loadbalancer name.
     * With name the ALB generate an alias without capital cars like mwaa-<randomnumber>.<region>.elb.amazonaws.com
     */
    const mwaaALB = new elb.ApplicationLoadBalancer(this, "ALB", {
      internetFacing: true,
      ipAddressType: elb.IpAddressType.IPV4,
      securityGroup: this.props.albSecurityGroup,
      vpc: this.props.mwaaVpc,
      loadBalancerName: "mwaa",
    });

    // Target group for IP addresses of MWAA
    const mwaaALBTargetGroup = new elb.ApplicationTargetGroup(
      this,
      "MwaaTargetGroup",
      {
        healthCheck: {
          enabled: true,
          healthyHttpCodes: "200,302",
          path: "/health",
        },
        protocol: elb.ApplicationProtocol.HTTPS,
        port: 443,
        targetType: elb.TargetType.IP,
        vpc: this.props.mwaaVpc,
      },
    );
    // Collect info about private IPs and add to the target group
    for (let index = 0; index < 4; index++) {
      const mwaaIp = new custom_resources.AwsCustomResource(
        this,
        `GetMwaaIp.${index}`,
        {
          onUpdate: {
            service: "EC2",
            action: "describeNetworkInterfaces",
            outputPaths: [`NetworkInterfaces.${index}.PrivateIpAddress`],
            parameters: {
              Filters: [
                {
                  Name: "group-id",
                  Values: this.props.mwaaSecurityGroupIds,
                },
                {
                  Name: "interface-type",
                  Values: ["vpc_endpoint"],
                },
              ],
            },
            physicalResourceId:
              custom_resources.PhysicalResourceId.fromResponse(
                `NetworkInterfaces.${index}.PrivateIpAddress`,
              ),
          },
          policy: custom_resources.AwsCustomResourcePolicy.fromSdkCalls({
            resources: custom_resources.AwsCustomResourcePolicy.ANY_RESOURCE,
          }),
        },
      );
      mwaaALBTargetGroup.addTarget(
        new elb_targets.IpTarget(
          mwaaIp.getResponseField(
            `NetworkInterfaces.${index}.PrivateIpAddress`,
          ),
        ),
      );
    }
    // Create lambda target group
    const mwaaAuthTargetGroup = new elb.ApplicationTargetGroup(
      this,
      "AuthLambda",
      {
        targets: [new elb_targets.LambdaTarget(authFunction)],
        targetType: elb.TargetType.LAMBDA,
        healthCheck: {
          enabled: false,
        },
      },
    );
    mwaaAuthTargetGroup.setAttribute(
      "lambda.multi_value_headers.enabled",
      "true",
    );
    // Import certificate form the ARN
    const certificate = acm.Certificate.fromCertificateArn(
      this,
      "Certificate",
      props.certificateArn,
    );

    // HTTPS Listener in ALB with Certificate
    const httpListener = mwaaALB.addListener("ALBHttpsListener", {
      certificates: [certificate],
      port: 443,
      protocol: elb.ApplicationProtocol.HTTPS,
      defaultAction: elb.ListenerAction.forward([mwaaALBTargetGroup]),
    });

    // Cognito userpool client
    const userPoolClient = new cognito.UserPoolClient(this, "UserPoolClient", {
      oAuth: {
        callbackUrls: [
          `https://${mwaaALB.loadBalancerDnsName}/oauth2/idpresponse`,
        ],
        flows: {
          authorizationCodeGrant: true,
        },
        logoutUrls: [`https://${mwaaALB.loadBalancerDnsName}/logout`],
        scopes: [cognito.OAuthScope.OPENID],
      },
      generateSecret: true,
      refreshTokenValidity: Duration.minutes(60),
      userPool: userPool,
    });

    // Rules for ALB
    const mwaaAuthAction = new elb_actions.AuthenticateCognitoAction({
      userPool: userPool,
      userPoolClient: userPoolClient,
      userPoolDomain: userPoolDomain,
      next: elb.ListenerAction.forward([mwaaAuthTargetGroup]),
    });
    // If we have login=true forward to the ALB
    httpListener.addAction("Login", {
      action: elb.ListenerAction.forward([mwaaALBTargetGroup]),
      conditions: [
        elb.ListenerCondition.pathPatterns([
          "/aws_mwaa/aws-console-sso",
          "/logout",
        ]),
        elb.ListenerCondition.queryStrings([{ value: "true", key: "login" }]),
      ],
      priority: 1,
    });
    // Auth rule with Cognito pool
    httpListener.addAction("Auth", {
      action: mwaaAuthAction,
      conditions: [
        elb.ListenerCondition.pathPatterns(["/aws_mwaa/aws-console-sso"]),
      ],
      priority: 2,
    });

    // Stack Outputs
    // Bug with transforming to lowercase, need to think about solution
    // https://github.com/aws/aws-cdk/issues/26103
    new CfnOutput(this, "ExternalURL", {
      description: "External url for access",
      value: `https://${mwaaALB.loadBalancerDnsName}/`,
    });

    new CfnOutput(this, "CognitoUserPoolId", {
      description: "Cognito User Pool ID",
      value: userPool.userPoolId,
    });

    // CDK NAG suppressions
    NagSuppressions.addResourceSuppressions(
      userPool,
      [
        {
          id: "AwsSolutions-COG1",
          reason:
            "False positive, there is no user pool. Only federation is in use.",
        },
        {
          id: "AwsSolutions-COG3",
          reason: "Temporary disable, need to check later.",
        },
      ],
      false,
    );
    NagSuppressions.addStackSuppressions(
      this,
      [
        {
          id: "AwsSolutions-IAM5",
          reason: "Custom resource. Need to check or replace in future.",
        },
        {
          id: "AwsSolutions-IAM4",
          reason:
            "Lambda function. False positive, this are default managed policies",
        },
        {
          id: "AwsSolutions-L1",
          reason: "Lambda function. False positive, we use python3.10",
        },
      ],
      false,
    );
    NagSuppressions.addResourceSuppressions(
      mwaaALB,
      [
        {
          id: "AwsSolutions-ELB2",
          reason: "For development purposes we disable this function.",
        },
      ],
      false,
    );
  }
}
