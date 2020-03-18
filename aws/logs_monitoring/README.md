# Datadog Forwarder

AWS Lambda function to ship logs from S3 and CloudWatch, custom metrics and traces from Lambda functions to Datadog.

## Features

- Forward CloudWatch, ELB, S3, CloudTrail, VPC and CloudFront logs to Datadog
- Forward S3 events to Datadog
- Forward Kinesis data stream events to Datadog, only CloudWatch logs are supported
- Forward custom metrics from AWS Lambda functions via CloudWatch logs
- Forward traces from AWS Lambda functions via CloudWatch logs
- Generate and submit enhanced Lambda metrics (`aws.lambda.enhanced.*`) parsed from the AWS REPORT log: duration, billed_duration, max_memory_used, and estimated_cost

## Installation

[![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?stackName=datadog-forwarder&templateURL=https://datadog-cloudformation-template.s3.amazonaws.com/aws/forwarder/latest.yaml)

1. Log into your admin AWS account/role and deploy the CloudFormation Stack with the button above.
1. Fill in `DdApiKey` and select the appropriate `DdSite`. All other parameters are optional.
1. Click **Create stack**, and wait for the creation to complete.
1. Find the installed forwarder Lambda function under the stack's "Resources" tab with logical ID `Forwarder`.
1. Set up triggers to the installed Forwarder either [automatically](https://docs.datadoghq.com/integrations/amazon_web_services/?tab=allpermissions#automatically-setup-triggers) or [manually](https://docs.datadoghq.com/integrations/amazon_web_services/?tab=allpermissions#manually-setup-triggers).
1. Repeat the above steps in another region if you operate in multiple AWS regions. 

## Updating

### Upgrade to a new version

1. Find the [datadog-forwarder (if you didn't rename it)](https://console.aws.amazon.com/cloudformation/home#/stacks?filteringText=datadog) CloudFormation stack.
1. Update the stack using template `https://datadog-cloudformation-template.s3.amazonaws.com/aws/forwarder/latest.yaml`. You can also replace `latest` with a specific version, e.g., `3.0.2.yaml`, if needed.

### Upgrade an older version to +3.0.0

Since version 3.0.0, the forwarder Lambda function is managed by CloudFormation. To upgrade an older forwarder installation to 3.0.0 and above, follow the steps below.

1. Install a new forwarder following the [installation](#installation) steps.
1. Find the installed forwarder Lambda function under the stack's "Resources" tab with logical ID `Forwarder`.
1. Manually migrate a few triggers (CloudWatch log group subscription filter and S3 bucket event notification) on the old forwarder to the new one.
1. Ensure the new forwarder is working as expected, i.e., being invoked regularly without errors.
1. Ensure the logs from the migrated triggers (sources) are showing up in Datadog log explorer and look right to you.
1. Migrate all triggers to the new forwarder.
   1. If you have been letting Datadog manage triggers [automatically](https://docs.datadoghq.com/integrations/amazon_web_services/?tab=allpermissions#automatically-setup-triggers) for you, update the forwarder Lambda ARN in AWS integration tile "Collect Logs" tab.
   1. If you have been manage the triggers [manually](https://docs.datadoghq.com/integrations/amazon_web_services/?tab=allpermissions#manually-setup-triggers), then you have to migrate them manually (or using a script).
1. Ensure the old forwarder Lambda function's invocations count drops to zero.
1. Delete the old forwarder Lambda function when you feel comfortable.
1. If you have old forwarder Lambda functions installed in multiple AWS accounts and regions, repeat the steps above in every account and region combination.

### Adjusting forwarder settings

1. Find the [datadog-forwarder (if you didn't rename it)](https://console.aws.amazon.com/cloudformation/home#/stacks?filteringText=datadog) CloudFormation stack.
1. Update the stack using the current template.
1. Adjust parameter values.

Note: It's recommended to adjust forwarder settings through CloudFormation rather than directly editing the Lambda function. The description of settings can be found in the [template.yaml](template.yaml) and the CloudFormation stack creation user interface when you launch the stack. Feel free to submit a pull request to make additional settings adjustable through the template.

## Settings

To view all the adjustable settings of the forwarder, click "Launch Stack" from the [Installation](#installation) section and you will be prompted with a CloudFormation user interface with all the adjustable settings (you do not have to complete the installation).

The technical definition of the settings can be found in the "Parameters" section of [template.yaml](template.yaml).

## Troubleshooting

Set the environment variable `DD_LOG_LEVEL` to `debug` on the Forwarder Lambda function to enable detailed logging temporarily (don't forget to remove it). If the debug logs don't help, please contact [Datadog support](https://www.datadoghq.com/support/).

## Notes

* For S3 logs, there may be some latency between the time a first S3 log file is posted and the Lambda function wakes up.
* Currently, the forwarder has to be deployed manually to GovCloud and China, and supports only log forwarding.
  1. Create a Lambda function using `aws-dd-forwarder-<VERSION>.zip` from the latest [releases](https://github.com/DataDog/datadog-serverless-functions/releases).
  1. Save your Datadog API key in AWS Secrets Manager, and set environment variable `DD_API_KEY_SECRET_ARN` with the secret ARN on the Lambda function.
  1. Configure [triggers](https://docs.datadoghq.com/integrations/amazon_web_services/?tab=allpermissions#send-aws-service-logs-to-datadog).
