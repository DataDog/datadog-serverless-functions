# Datadog Forwarder

AWS Lambda function to ship logs and metrics from ELB, S3, CloudTrail, VPC, CloudFront and CloudWatch logs to Datadog

# Features

- Forward logs through HTTPS (defaulted to port 443)
- Use AWS Lambda to re-route triggered S3 events to Datadog
- Use AWS Lambda to re-route triggered Kinesis data stream events to Datadog, only the Cloudwatch logs are supported
- Cloudwatch, ELB, S3, CloudTrail, VPC and CloudFont logs can be forwarded
- JSON events providing details about S3 documents forwarded
- Structured meta-information can be attached to the events
- Scrubbing / Redaction rules
- Filtering rules (`INCLUDE_AT_MATCH` and `EXCLUDE_AT_MATCH`)
- Multiline Log Support (S3 Only)
- Forward custom metrics from logs

# Quick Start

The provided Python script must be deployed into your AWS Lambda service. We will explain how in this step-by-step tutorial.

## 1. Create a new Lambda function

- Navigate to the Lambda console: https://console.aws.amazon.com/lambda/home and create a new function.
- Select `Author from scratch` and give the function a unique name.
- For `Role`, select `Create new role from template(s)` and give the role a unique name.
- Under Policy templates, search for and select `s3 object read-only permissions`.

## 2. Provide the code

- Copy paste the code of the Lambda function
- Set the runtime to `Python 2.7`, `Python 3.6`, or `Python 3.7`
- Set the handler to `lambda_function.lambda_handler`


### Parameters

At the top of the script you'll find a section called `#Parameters`, that's where you want to edit your code.

```
#Parameters
ddApiKey = "<your_api_key>"
# metadata: Additional metadata to send with the logs
metadata = {
    "ddsourcecategory": "aws"
}
```

- **API key**:

There are 3 possibilities to set your Datadog's API key (available in your Datadog platform):

1. **KMS Encrypted key (recommended)**: Use the `DD_KMS_API_KEY` environment variable to use a KMS encrypted key. Make sure that the Lambda excution role is listed in the KMS Key user in https://console.aws.amazon.com/iam/home#encryptionKeys.
2. **Environment Variable**: Use the `DD_API_KEY` environment variable of the Lambda function
3. **Manual**: Replace `<your_api_key>` in the code:

- **(Optional) Metadata**:

You can optionally change the structured metadata. The metadata is merged to all the log events sent by the Lambda script.
Example adding the environment (`env`) value to your logs:

```
metadata = {
    "ddsourcecategory": "aws",
    "env": "prod",
}
```

- **(Optional) Custom Tags**

You have two options to add custom tags to your logs:

- Manually by editing the lambda code [here](https://github.com/DataDog/datadog-serverless-functions/blob/master/aws/logs_monitoring/lambda_function.py#L418-L423).
- Automatically with the `DD_TAGS` environment variable (tags must be a comma-separated list of strings).

## 3. (optional) Send logs to EU or to a proxy

### Send logs through TCP

By default, the forwarder sends logs using HTTPS through the port 443. 

To send logs over a SSL encrypted TCP connection, set the environment variable `DD_USE_TCP` to `true`.

### Send logs to EU

Set the environment variable `DD_SITE` to `datadoghq.eu` and logs are automatically forwarded to your EU platform.

### Send logs through a proxy

For TCP, ensure that you disable SSL between the lambda and your proxy by setting `DD_NO_SSL` to `true`
 
Two environment variables can be used to forward logs through a proxy:

- `DD_URL`: Define the proxy endpoint to forward the logs to
- `DD_PORT`: Define the proxy port to forward the logs to

## 4. Configuration

- Set the memory to the highest possible value.
- Also set the timeout limit. We recommends 120 seconds to deal with big files.
- Hit the `Save and Test` button.

## 5. Testing it

If the test "succeeded", you are all set! The test log will not show up in the platform.

For S3 logs, there may be some latency between the time a first S3 log file is posted and the Lambda function wakes up.

## 6. (optional) Scrubbing / Redaction rules

Multiple scrubbing options are available.  `REDACT_IP` and `REDACT_EMAIL` match against hard-coded patterns, while `DD_SCRUBBING_RULE` allows users to supply a regular expression.  
- To use `REDACT_IP`, add it as an environment variable and set the value to `true`.  
    - Text matching `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` will be replaced with `xxx.xxx.xxx.xxx`.
- To use `REDACT_EMAIL`, add it as an environment variable and set the value to `true`.
	- Text matching `[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+` will be replaced with `xxxxx@xxxxx.com`.
- To use `DD_SCRUBBING_RULE`, add it as a environment variable, and supply a regular expression as the value.
    - Text matching the user-supplied regular expression will be replaced with `xxxxx`, by default. 
    - Use the `DD_SCRUBBING_RULE_REPLACEMENT` environment variable to supply a replacement value instead of `xxxxx`.  
- Scrubbing rules are applied to the full JSON-formatted log, including any metadata that is automatically added by the Lambda function.
- Each instance of a pattern match is replaced until no more matches are found in each log. 

## 7. (optional) Filtering rules

Use the `EXCLUDE_AT_MATCH` OR `INCLUDE_AT_MATCH` environment variables to filter logs based on a regular expression match.

- To use `EXCLUDE_AT_MATCH` add it as an environment variable and set its value to a regular expression. Logs matching the regular expression will be excluded.
- To use `INCLUDE_AT_MATCH` add it as an environment variable and set its value to a regular expression. If not excluded by `EXCLUDE_AT_MATCH`, logs matching the regular expression will be included.
- If a log matches both the inclusion and exclusion criteria, it will be excluded.
- Filtering rules are applied to the full JSON-formatted log, including any metadata that is automatically added by the function.

## 8. (optional) Multiline Log support for s3

If there are multiline logs in s3, set `DD_MULTILINE_LOG_REGEX_PATTERN` environment variable to the specified regex pattern to detect for a new log line.

- Example: for multiline logs beginning with pattern `11/10/2014`: `DD_MULTILINE_LOG_REGEX_PATTERN="\d{2}\/\d{2}\/\d{4}"`

## 9. (optional) Forward Metrics from Logs

For example, if you have a Lambda function that powers a performance-critical task (e.g., a consumer-facing API), you can avoid the added latencies of submitting metric via API calls, by writing custom metrics to CloudWatch Logs using the appropriate Datadog Lambda Layer (e.g., [Lambda Layer for Python](https://github.com/DataDog/datadog-lambda-layer-python)). The log forwarder will automatically detect log entries that contain metrics and forward them to Datadog metric intake.

The [Datadog Lambda Layer for Python 2.7, 3.6, or 3.7]((https://github.com/DataDog/datadog-lambda-layer-python)) **MUST** be added to the log forwarder Lambda function, to enable metric forwarding. Use the Lambda layer ARN below, and replace `us-east-1` with the actual AWS region where your log forwarder operates and replace `Python27` with the Python runtime your function uses (`Python27`, `Python36`, or `Python37`).

```
arn:aws:lambda:us-east-1:464622532012:layer:Datadog-Python27:5
```

**IMPORTANT**

The log forwarder **ALWAYS** forwards logs by default. If you do NOT use the Datadog log management product, you **MUST** set environment variable `DD_FORWARD_LOG` to `False`, to avoid sending logs to Datadog. The log forwarder will then only forward metrics.
