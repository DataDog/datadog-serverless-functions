**IMPORTANT NOTE: When upgrading, please ensure your forwarder Lambda function has [the latest Datadog Lambda Layer installed](https://github.com/DataDog/datadog-serverless-functions/tree/master/aws/logs_monitoring#3-add-the-datadog-lambda-layer).**

# Datadog Forwarder

AWS Lambda function to ship logs and metrics from ELB, S3, CloudTrail, VPC, CloudFront, and CloudWatch logs to Datadog

## Features

- Forward logs through HTTPS (defaulted to port 443)
- Use AWS Lambda to re-route triggered S3 events to Datadog
- Use AWS Lambda to re-route triggered Kinesis data stream events to Datadog, only the Cloudwatch logs are supported
- Cloudwatch, ELB, S3, CloudTrail, VPC and CloudFront logs can be forwarded
- SSL Security
- JSON events providing details about S3 documents forwarded
- Structured meta-information can be attached to the events
- Scrubbing / Redaction rules
- Filtering rules (`INCLUDE_AT_MATCH` and `EXCLUDE_AT_MATCH`)
- Multiline Log Support (S3 Only)
- Forward custom metrics from logs
- Submit `aws.lambda.enhanced.*` Lambda metrics parsed from the AWS REPORT log: duration, billed_duration, max_memory_used, estimated_cost

## Quick Start

The provided Python script must be deployed into your AWS Lambda service to collect your logs and send them to Datadog.

### 1. Create a new Lambda function

1. [Navigate to the Lambda console](https://console.aws.amazon.com/lambda/home) and create a new function.
2. Select `Author from scratch` and give the function a unique name: `datadog-log-monitoring-function`
3. For `Role`, select `Create new role from template(s)` and give the role a unique name: `datadog-log-monitoring-function-role`
4. Under Policy templates, select `s3 object read-only permissions`.

### 2. Provide the code

1. Copy paste the code of the Lambda function from the `lambda_function.py` file.
2. Set the runtime to `Python 2.7`, `Python 3.6`, or `Python 3.7`
3. Set the handler to `lambda_function.lambda_handler`

### 3. Add the Datadog Lambda Layer
The [Datadog Lambda Layer]((https://github.com/DataDog/datadog-lambda-layer-python)) **MUST** be added to the log forwarder Lambda function. Use the Lambda layer ARN below, and replace `<AWS_REGION>` with the actual region (e.g., `us-east-1`), `<PYTHON_RUNTIME>` with the runtime of your forwarder (e.g., `Python27`), and `<VERSION>` with the latest version from the [CHANGELOG](https://github.com/DataDog/datadog-lambda-layer-python/blob/master/CHANGELOG.md).

```
arn:aws:lambda:<AWS_REGION>:464622532012:layer:Datadog-<PYTHON_RUNTIME>:<VERSION>
```

For example:

```
arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Python37:8
```


### 4. Set your Parameters

At the top of the script you'll find a section called `PARAMETERS`, that's where you want to edit your code, available paramters are:

#### DD_API_KEY

Set the Datadog API key for your Datadog platform, it can be found here:

* Datadog US Site: https://app.datadoghq.com/account/settings#api
* Datadog EU Site: https://app.datadoghq.eu/account/settings#api

There are 3 possibilities to set your Datadog API key:

1. **KMS Encrypted key (recommended)**: Use the `DD_KMS_API_KEY` environment variable to use a KMS encrypted key. Make sure that the Lambda execution role is listed in the KMS Key user in https://console.aws.amazon.com/iam/home#encryptionKeys.
2. **Environment Variable**: Use the `DD_API_KEY` environment variable for the Lambda function.
3. **Manual**: Replace `<YOUR_DATADOG_API_KEY>` in the code:

  ```python
  ## @param DD_API_KEY - String - required - default: none
  ## The Datadog API key associated with your Datadog Account
  ## It can be found here:
  ##
  ##   * Datadog US Site: https://app.datadoghq.com/account/settings#api
  ##   * Datadog EU Site: https://app.datadoghq.eu/account/settings#api
  #
  DD_API_KEY = "<YOUR_DATADOG_API_KEY>"
  ```

#### Custom Tags

Add custom tags to all data forwarded by your function, either:

* Use the `DD_TAGS` environment variable. Your tags must be a comma-separated list of strings with no trailing comma.
* Edit the lambda code directly:

  ```python
  ## @param DD_TAGS - list of comma separated strings - optional -default: none
  ## Pass custom tags as environment variable or through this variable.
  ## Ensure your tags are a comma separated list of strings with no trailing comma in the envvar!
  #
  DD_TAGS = os.environ.get("DD_TAGS", "")
  ```

#### Datadog Site

Define your Datadog Site to send data to, `datadoghq.com` for Datadog US site or `datadoghq.eu` for Datadog EU site, either:

* Use the `DD_SITE` environment variable.
* Edit the lambda code directly:

  ```python
  ## @param DD_SITE - String - optional -default: datadoghq.com
  ## Define the Datadog Site to send your logs and metrics to.
  ## Set it to `datadoghq.eu` to send your logs and metrics to Datadog EU site.
  #
  DD_SITE = os.getenv("DD_SITE", default="datadoghq.com")
  ```

#### Send logs through TCP or HTTP.

By default, the forwarder sends logs using HTTPS through the port `443`. To send logs over a SSL encrypted TCP connection either:

* Set the environment variable `DD_USE_TCP` to `true`.
* Edit the lambda code directly:

  ```python
  ## @param DD_USE_TCP - boolean - optional -default: false
  ## Change this value to `true` to send your logs and metrics using the HTTP network client
  ## By default, it use the TCP client.
  #
  DD_USE_TCP = os.getenv("DD_USE_TCP", default="false").lower() == "true"
  ```

#### Proxy

Ensure that you disable SSL between the lambda and your proxy by setting `DD_NO_SSL` to `true`
 
Two environment variables can be used to forward logs through a proxy:

* `DD_URL`: Define the proxy endpoint to forward the logs to.
* `DD_PORT`: Define the proxy port to forward the logs to.

#### DD_FETCH_LAMBDA_TAGS

If the `DD_FETCH_LAMBDA_TAGS` env variable is set to `true` then the log forwarder will fetch Lambda tags using [GetResources](https://docs.aws.amazon.com/resourcegroupstagging/latest/APIReference/API_GetResources.html) API calls and apply them to the `aws.lambda.enhanced.*` metrics parsed from the REPORT log. For this to work the log forwarder function needs to be given the `tag:GetResources` permission. The tags are cached in memory so that they'll only be fetched when the function cold starts or when the TTL (1 hour) expires. The log forwarder increments the `aws.lambda.enhanced.get_resources_api_calls` metric for each API call made.

### 5. Configure your function

To configure your function:

1. Set the memory to 1024 MB.
2. Also set the timeout limit. 120 seconds is recommended to deal with big files.
3. Hit the `Save` button.

### 6. Test it

Hit the `Test` button, and select `CloudWatch Logs` as the sample event. If the test "succeeded", you are all set! The test log doesn't show up in the platform.

**Note**: For S3 logs, there may be some latency between the time a first S3 log file is posted and the Lambda function wakes up.

### 7. (optional) Scrubbing / Redaction rules

Multiple scrubbing options are available.  `REDACT_IP` and `REDACT_EMAIL` match against hard-coded patterns, while `DD_SCRUBBING_RULE` allows users to supply a regular expression.
- To use `REDACT_IP`, add it as an environment variable and set the value to `true`.
    - Text matching `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` is replaced with `xxx.xxx.xxx.xxx`.
- To use `REDACT_EMAIL`, add it as an environment variable and set the value to `true`.
	- Text matching `[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+` is replaced with `xxxxx@xxxxx.com`.
- To use `DD_SCRUBBING_RULE`, add it as a environment variable, and supply a regular expression as the value.
    - Text matching the user-supplied regular expression is replaced with `xxxxx`, by default.
    - Use the `DD_SCRUBBING_RULE_REPLACEMENT` environment variable to supply a replacement value instead of `xxxxx`.
- Scrubbing rules are applied to the full JSON-formatted log, including any metadata that is automatically added by the Lambda function.
- Each instance of a pattern match is replaced until no more matches are found in each log.

### 8. (optional) Filtering rules

Use the `EXCLUDE_AT_MATCH` OR `INCLUDE_AT_MATCH` environment variables to filter logs based on a regular expression match:

- To use `EXCLUDE_AT_MATCH` add it as an environment variable and set its value to a regular expression. Logs matching the regular expression are excluded.
- To use `INCLUDE_AT_MATCH` add it as an environment variable and set its value to a regular expression. If not excluded by `EXCLUDE_AT_MATCH`, logs matching the regular expression are included.
- If a log matches both the inclusion and exclusion criteria, it is excluded.
- Filtering rules are applied to the full JSON-formatted log, including any metadata that is automatically added by the function.

### 9. (optional) Multiline Log support for s3

If there are multiline logs in s3, set `DD_MULTILINE_LOG_REGEX_PATTERN` environment variable to the specified regex pattern to detect for a new log line.

- Example: for multiline logs beginning with pattern `11/10/2014`: `DD_MULTILINE_LOG_REGEX_PATTERN="\d{2}\/\d{2}\/\d{4}"`

### 10. (optional) Disable log forwarding

The datadog forwarder **ALWAYS** forwards logs by default. If you do NOT use the Datadog log management product, you **MUST** set environment variable `DD_FORWARD_LOG` to `False`, to avoid sending logs to Datadog. The forwarder will then only forward other observability data, such as metrics.

### 11. (optional) Disable SSL validation

If you need to ignore SSL certificate validation when forwarding logs using HTTPS, you can set the environment variable `DD_SKIP_SSL_VALIDATION` to `True`.
This will still encrypt the traffic between the forwarder and the endpoint provided with `DD_URL` but will not check if the destination SSL certificate is valid. 
