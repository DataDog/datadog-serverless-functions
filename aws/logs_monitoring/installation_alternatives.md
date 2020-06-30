# Datadog Forwarder Installation Alternatives

## Terraform Installation

The Forwarder can be installed using the Terraform resource [aws_cloudformation_stack](https://www.terraform.io/docs/providers/aws/r/cloudformation_stack.html) as a wrapper on top of the provided CloudFormation template.

<details><summary>Sample Configuration</summary>

```tf
variable "dd_api_key" {
  type        = string
  description = "Datadog API key"
}

resource "aws_secretsmanager_secret" "dd_api_key" {
  name        = "datadog_api_key"
  description = "Datadog API Key"
}

resource "aws_secretsmanager_secret_version" "dd_api_key" {
  secret_id     = aws_secretsmanager_secret.dd_api_key.id
  secret_string = var.dd_api_key
}

resource "aws_cloudformation_stack" "datadog-forwarder" {
  name         = "datadog-forwarder"
  capabilities = ["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"]
  parameters   = {
    DdApiKey           = "value_will_be_overwritten_by_DdApiKeySecretArn"
    DdApiKeySecretArn  = aws_secretsmanager_secret.dd_api_key.arn
    FunctionName       = "datadog-forwarder"
  }
  template_url = "https://datadog-cloudformation-template.s3.amazonaws.com/aws/forwarder/latest.yaml"
  
}

# Example Cloudwatch Logs subscription for AWS Batch

variable "aws_region" {
  type        = string
  description = "AWS Region"
  default     = "us-east-1"
}

variable "account_id" {
  type = string
  description = "AWS Account Id"
}

resource "aws_cloudwatch_log_subscription_filter" "aws_batch" {
  name                  = "aws_batch"
  log_group_name        = "/aws/batch/job"
  destination_arn       = aws_cloudformation_stack.datadog-forwarder.outputs["DatadogForwarderArn"]
  filter_pattern        = ""
}

resource "aws_lambda_permission" "datadog_forwarder" {
    action         = "lambda:InvokeFunction"
    function_name  = aws_cloudformation_stack.datadog-forwarder.outputs["DatadogForwarderArn"]
    principal      = "logs.${var.aws_region}.amazonaws.com"
    source_account = var.account_id
    source_arn     = "arn:aws:logs:${var.aws_region}:${var.account_id}:log-group:/aws/batch/job:*"
}


```

</details>


## Manual Installation

If for some reason you cannot install the forwarder using the provided CloudFormation template, you can install the forwarder manually following the steps below. Feel free to open an issue or pull request to let us know if there is anything we can improve to make the template work for you.

<details><summary>Steps</summary>

1. Create a Python 3.7 Lambda function using `aws-dd-forwarder-<VERSION>.zip` from the latest [releases](https://github.com/DataDog/datadog-serverless-functions/releases).
1. Save your Datadog API key in AWS Secrets Manager, set environment variable `DD_API_KEY_SECRET_ARN` with the secret ARN on the Lambda function, and add the `secretsmanager:GetSecretValue` permission to the Lambda execution role.
1. If you need to forward logs from S3 buckets, add the `s3:GetObject` permission to the Lambda execution role.
1. Set environment variable `DD_ENHANCED_METRICS` to `false` on the forwarder. This stops the forwarder from generating enhanced metrics itself, but it will still forward custom metrics from other lambdas.
1. Configure [triggers](https://docs.datadoghq.com/integrations/amazon_web_services/?tab=allpermissions#send-aws-service-logs-to-datadog).

</details>
