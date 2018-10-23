# aws-lambda functions
Repository of lambda functions that process aws log streams and send data to datadog


# Overview
This project contains lambda functions to be used to process aws log streams and send data
to datadog.

Each lambda function will retrieve datadog api keys from KMS.


# How to use one of these functions

1. Create a KMS key for the datadog api key and app key
   - Create a KMS key - http://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html
   - Encrypt the token using the AWS CLI.`aws kms encrypt --key-id alias/<KMS key name> --plaintext '{"api_key":"<dd_api_key>", "app_key":"<dd_app_key>"}'`
   - Make sure to save the base-64 encoded, encrypted key (CiphertextBlob). This will be used for the `KMS_ENCRYPTED_KEYS` variable in all lambda functions.

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

   - Create a lambda function: Skip the blueprint, name it `functionname`, set the Runtime to `Python 2.7`, the handle to `lambda_function.lambda_handler`, and the role to `lambda_execution`.

   - Copy the content of `functionname/lambda_function.py` in the code section, make sure to update the `KMS_ENCRYPTED_KEYS` environment variable with the encrypted key generated in step 1

1. Subscribe to the appropriate log stream


# How to update the zip file for the AWS Serverless Apps

1. After modifying the files that you want inside the respective lambda app directory, run
```
aws cloudformation package --template-file rds-enhanced-sam-template.yaml --output-template-file rds-enhanced-serverless-output.yaml --s3-bucket BUCKET_NAME
```
