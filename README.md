# dd-aws-lambda-functions
Repository of lambda functions that process aws log streams and send data to datadog


# Overview
This project contains lambda functions to be used to process aws log streams and send data
to datadog, along with some small tools to easily update these lambda functions in a dev
environment.

The development process is to have a lambda function based on a zip file hosted on amazon s3.
To publish a new version of the function, one updates the zip file, pushes it to s3, and updates
the lambda function.

Each lambda function will retrieve datadog api keys from KMS.


# Getting started

1. install awscli
   ```
   pip install awscli
   ```
   You'll need write access to a s3 bucket, and to be able to call `lambda:UpdateFunctionCode`

1. Generate `base.zip`
   ```
   rake build-base
   ```
   `base.zip` contains datadogpy and it's dependencies.


# Create a new function

1. Create a KMS key for the datadog api key and app key
  - Create a KMS key - http://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html
  - Encrypt the token using the AWS CLI.`aws kms encrypt --key-id alias/<KMS key name> --plaintext '{"api_key":"<dd_api_key>", "app_key":"<dd_app_key>"}'`
  - Copy the base-64 encoded, encrypted key (CiphertextBlob) to the KMS_ENCRYPTED_KEYS variable.


1. Create and configure a lambda function
  - In the AWS Console, create a `lambda_execution` policy, with the following policy:
    ```
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "arn:aws:logs:*:*:*"
            },
            {
                 "Effect": "Allow",
                 "Action": [
                   "kms:Decrypt"
                 ],
                 "Resource": [
                   "<KMS ARN>"
                 ]
               }
        ]
    }
    ```

  - Create a `lambda_execution` role and attach this policy

  - Create a lambda function named `functionname`, with `main.send_metric` as the handler, and the `lambda_execution` role.

  - Subscribe to the appropriate log stream

1. Initialize the function folder
   ```
   rake init[functionname]
   ```

# Update an existing function

- Double check that the KMS secret in `main.py` is up to date

- Update the function
  ```
  rake push[functionname,bucket]
  ```

