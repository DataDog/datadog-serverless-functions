# Datadog-lambda


AWS lambda function to ship ELB, S3, CloudTrail, VPC, CloudFront and CloudWatch logs to Datadog

# Features

- Use AWS Lambda to re-route triggered S3 events to Datadog
- ELB, S3, CloudTrail, VPC and CloudFont logs can be forwarded
- SSL Security
- JSON events providing details about S3 documents forwarded
- Structured meta-information can be attached to the events

# Quick Start

The provided Python script must be deployed into your AWS Lambda service. We will explain how in this step-by-step tutorial.

## 1. Create a new Lambda function

- Navigate to the Lambda console: https://console.aws.amazon.com/lambda/home and create a new function.
- Select `Author from scratch` and give the function a unique name.
- For `Role`, select `Create new role from template(s)` and give the role a unique name.
- Under Policy templates, search for and select `s3 object read-only permissions`.

## 2. Provide the code

- Copy paste the code of the Lambda function
- Set the runtime to `Python 2.7`
- Set the handler to `lambda_function.lambda_handler`


### Parameters

At the top of the script you'll find a section called `#Parameters`, that's where you want to edit your code.

```
#Parameters
ddApiKey = "<your_api_key>"
metadata = {"context":{"foo": "bar"}}
```

- **API key**:

Replace `<your_api_key>`: Your Datadog's API key is available in your platform.
You can also set it thanks to the `DD_API_KEY` environment variable.

- **metadata**:

You can optionally change the structured metadata. The metadata is merged to all the log events sent by the Lambda script.

## 3. Configuration

- Set the memory to the highest possible value.
- Set also the timeout limit. We recommends 120 seconds to deal with big files.
- Hit the `Save and Test` button.

## 4. Testing it

You are all set!

The test should be quite natural if the pointed bucket(s) are filling up. There may be some latency between the time a S3 log file is posted and the Lambda function wakes up.
