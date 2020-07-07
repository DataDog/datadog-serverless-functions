# Datadog Forwarder Installation Alternatives

## Terraform Installation

The Forwarder can be installed using the Terraform resource [aws_cloudformation_stack](https://www.terraform.io/docs/providers/aws/r/cloudformation_stack.html) as a wrapper on top of the provided CloudFormation template. 

You are recommended to create two separate Terraform configurations. You first store the Datadog API key in the AWS Secrets Manager, and note down the secrets ARN from the output of apply. Then you create another configuration for the forwarder and supply the secrets ARN through the `DdApiKeySecretArn` parameter. By separating the configurations of the API key and the forwarder, you avoid being asked to provide the Datadog API key when updating the forwarder. Note, the `DdApiKey` parameter is required by the CloudFormation template, so you need to give it a placeholder value (any value) in order to apply. To update or upgrade the forwarder in the future, you simply apply the forwarder configuration again.

<details><summary>Sample Configuration</summary>

```tf
# Store Datadog API key in AWS Secrets Manager
variable "dd_api_key" {
  type        = string
  description = "Datadog API key"
}

resource "aws_secretsmanager_secret" "dd_api_key" {
  name        = "datadog_api_key"
  description = "Encrypted Datadog API Key"
}

resource "aws_secretsmanager_secret_version" "dd_api_key" {
  secret_id     = aws_secretsmanager_secret.dd_api_key.id
  secret_string = var.dd_api_key
}

output "dd_api_key" {
  value = aws_secretsmanager_secret.dd_api_key.arn
}
```

```tf
# Datadog Forwarder to ship logs from S3 and CloudWatch, as well as observability data from Lambda functions to Datadog.
# https://github.com/DataDog/datadog-serverless-functions/tree/master/aws/logs_monitoring
resource "aws_cloudformation_stack" "datadog_forwarder" {
  name         = "datadog-forwarder"
  capabilities = ["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"]
  parameters   = {
    DdApiKey           = "this_value_is_not_used"
    DdApiKeySecretArn  = "REPLACE ME WITH THE SECRETS ARN"
    FunctionName       = "datadog-forwarder"
  }
  template_url = "https://datadog-cloudformation-template.s3.amazonaws.com/aws/forwarder/latest.yaml"
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
