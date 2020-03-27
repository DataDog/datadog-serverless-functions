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

<details><summary>Steps</summary>

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

</details>

### Adjusting forwarder settings

1. Find the [datadog-forwarder (if you didn't rename it)](https://console.aws.amazon.com/cloudformation/home#/stacks?filteringText=datadog) CloudFormation stack.
1. Update the stack using the current template.
1. Adjust parameter values.

Note: It's recommended to adjust forwarder settings through CloudFormation rather than directly editing the Lambda function. The description of settings can be found in the [template.yaml](template.yaml) and the CloudFormation stack creation user interface when you launch the stack. Feel free to submit a pull request to make additional settings adjustable through the template.

## Deletion

To safely delete the forwarder and other AWS resources created by the forwarder CloudFormation stack, follow the steps below.

1. Find the [datadog-forwarder (if you didn't rename it)](https://console.aws.amazon.com/cloudformation/home#/stacks?filteringText=datadog) CloudFormation stack. Or you can find the stack from the forwarder Lambda function's management console by clicking the link from the message "This function belongs to an application. Click here to manage it.", and then click the "Deployments" tab on the application page.
1. "Delete" the CloudFormation stack.

## Settings

To view all the adjustable settings of the forwarder, click "Launch Stack" from the [Installation](#installation) section and you will be prompted with a CloudFormation user interface with all the adjustable settings (you do not have to complete the installation).

The technical definition of the settings can be found in the "Parameters" section of [template.yaml](template.yaml).

## Troubleshooting

Set the environment variable `DD_LOG_LEVEL` to `debug` on the Forwarder Lambda function to enable detailed logging temporarily (don't forget to remove it). If the debug logs don't help, please contact [Datadog support](https://www.datadoghq.com/support/).

## Manual Installation

If for some reason you cannot install the forwarder using the provided CloudFormation template (e.g., AWS China or GovCloud), you can install the forwarder manually following the steps below. Feel free to open an issue or pull request to let us know if there is anything we can improve to make the template work for you.

<details><summary>Steps</summary>

1. Create a Python3.7 Lambda function using `aws-dd-forwarder-<VERSION>.zip` from the latest [releases](https://github.com/DataDog/datadog-serverless-functions/releases).
1. Save your Datadog API key in AWS Secrets Manager, set environment variable `DD_API_KEY_SECRET_ARN` with the secret ARN on the Lambda function, and add the `secretsmanager:GetSecretValue` permission to the Lambda execution role.
1. If you need to forward logs from S3 buckets, add the `s3:GetObject` permission to the Lambda execution role.
1. If you need to forward custom metrics and traces from your Lambda functions' logs for serverless monitoring (not yet supported in AWS China and GovCloud), attach these [layers](https://github.com/DataDog/datadog-serverless-functions/blob/3639499bf602ea3d04493028aa08d1076cc02234/aws/logs_monitoring/template.yaml#L264) (switch to master branch for the latest layer versions) to the forwarder, and set environment variable `DD_ENHANCED_METRICS` to `false` on the forwarder.
1. Configure [triggers](https://docs.datadoghq.com/integrations/amazon_web_services/?tab=allpermissions#send-aws-service-logs-to-datadog).

</details>

## Terraform Installation

The forwarder can be installed using Terraform resource [aws_cloudformation_stack](https://www.terraform.io/docs/providers/aws/r/cloudformation_stack.html) as a wrapper on top of the provided CloudFormation template.

<details><summary>Sample Configuration</summary>

```tf
variable "dd_api_key" {
  type        = string
  description = "Datadog API key"
}

resource "aws_cloudformation_stack" "datadog-forwarder" {
  name         = "datadog-forwarder"
  capabilities = ["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"]
  parameters   = {
    DdApiKey        = var.dd_api_key
    FunctionName    = "datadog-forwarder"
  }
  template_url = "https://datadog-cloudformation-template.s3.amazonaws.com/aws/forwarder/latest.yaml"
}
```

</details>

## Permissions

To deploy the CloudFormation stack with the default options, you need to have the permissions below to save Datadog API key as a secret, create a S3 bucket to store the forwarder's zip (source code), and create Lambda functions (including execution roles and log groups).

<details><summary>IAM Statements</summary>

```json
{
   "Effect": "Allow",
   "Action": [
         "cloudformation:*",
         "secretsmanager:CreateSecret",
         "secretsmanager:TagResource",
         "s3:CreateBucket",
         "s3:GetObject",
         "iam:CreateRole",
         "iam:GetRole",
         "iam:PassRole",
         "iam:PutRolePolicy",
         "iam:AttachRolePolicy",
         "lambda:CreateFunction",
         "lambda:GetFunction",
         "lambda:GetFunctionConfiguration",
         "lambda:GetLayerVersion",
         "lambda:InvokeFunction",
         "lambda:PutFunctionConcurrency",
         "lambda:AddPermission",
         "logs:CreateLogGroup",
         "logs:DescribeLogGroups",
         "logs:PutRetentionPolicy"
   ],
   "Resource": "*"
}
```

</details>

The CloudFormation stack creates following IAM roles:

- ForwarderRole: The execution role for the Forwarder Lambda function to read logs from S3, fetch Datadog API key from Secrets Manager and write its own logs.
  <details><summary>IAM Statements</summary>

  ```json
   [
      {
         "Effect": "Allow",
         "Action": [
               "logs:CreateLogGroup",
               "logs:CreateLogStream",
               "logs:PutLogEvents"
         ],
         "Resource": "*"
      },
      {
         "Action": [
               "s3:GetObject"
         ],
         "Resource": "arn:aws:s3:::*",
         "Effect": "Allow"
      },
      {
         "Action": [
               "secretsmanager:GetSecretValue"
         ],
         "Resource": "<ARN of DdApiKeySecret>",
         "Effect": "Allow"
      }
   ]
  ```

  </details>
- ForwarderZipCopierRole: The execution role for the ForwarderZipCopier Lambda function to download the Forwarder deployment zip file to a S3 bucket.
  <details><summary>IAM Statements</summary>

  ```json
   [
      {
         "Effect": "Allow",
         "Action": [
               "logs:CreateLogGroup",
               "logs:CreateLogStream",
               "logs:PutLogEvents"
         ],
         "Resource": "*"
      },
      {
         "Action": [
               "s3:PutObject",
               "s3:DeleteObject"
         ],
         "Resource": "<S3Bucket to Store the Forwarder Zip>",
         "Effect": "Allow"
      },
      {
         "Action": [
               "s3:ListBucket"
         ],
         "Resource": "<S3Bucket to Store the Forwarder Zip>",
         "Effect": "Allow"
      }
   ]
  ```

  </details>


## Notes

* For S3 logs, there may be some latency between the time a first S3 log file is posted and the Lambda function wakes up.
* Currently, the forwarder has to be deployed [manually](#manual-installation) to GovCloud and China, and supports only log forwarding.
