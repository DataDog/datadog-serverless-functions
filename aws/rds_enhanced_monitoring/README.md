# rds_enhanced_monitoring
Process a RDS enhanced monitoring DATA_MESSAGE, coming from CLOUDWATCH LOGS

# RDS message example
```json
    {
        "engine": "Aurora",
        "instanceID": "instanceid",
        "instanceResourceID": "db-QPCTQVLJ4WIQPCTQVLJ4WIJ4WI",
        "timestamp": "2016-01-01T01:01:01Z",
        "version": 1.00,
        "uptime": "10 days, 1:53:04",
        "numVCPUs": 2,
        "cpuUtilization": {
            "guest": 0.00,
            "irq": 0.00,
            "system": 0.88,
            "wait": 0.54,
            "idle": 97.57,
            "user": 0.68,
            "total": 1.56,
            "steal": 0.07,
            "nice": 0.25
        },
        "loadAverageMinute": {
            "fifteen": 0.14,
            "five": 0.17,
            "one": 0.18
        },
        "memory": {
            "writeback": 0,
            "hugePagesFree": 0,
            "hugePagesRsvd": 0,
            "hugePagesSurp": 0,
            "cached": 11742648,
            "hugePagesSize": 2048,
            "free": 259016,
            "hugePagesTotal": 0,
            "inactive": 1817176,
            "pageTables": 25808,
            "dirty": 660,
            "mapped": 8087612,
            "active": 13016084,
            "total": 15670012,
            "slab": 437916,
            "buffers": 272136
        },
        "tasks": {
            "sleeping": 223,
            "zombie": 0,
            "running": 1,
            "stopped": 0,
            "total": 224,
            "blocked": 0
        },
        "swap": {
            "cached": 0,
            "total": 0,
            "free": 0
        },
        "network": [{
            "interface": "eth0",
            "rx": 217.57,
            "tx": 2319.67
        }],
        "diskIO": [{
            "readLatency": 0.00,
            "writeLatency": 1.53,
            "writeThroughput": 2048.20,
            "readThroughput": 0.00,
            "readIOsPS": 0.00,
            "diskQueueDepth": 0,
            "writeIOsPS": 5.83
        }],
        "fileSys": [{
            "used": 7006720,
            "name": "rdsfilesys",
            "usedFiles": 2650,
            "usedFilePercent": 0.13,
            "maxFiles": 1966080,
            "mountPoint": "/rdsdbdata",
            "total": 30828540,
            "usedPercent": 22.73
        }],
        "processList": [{
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.00,
            "id": 8455,
            "rss": 10487696
        }, {
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.82,
            "id": 8782,
            "rss": 10487696
        }, {
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.05,
            "id": 8784,
            "rss": 10487696
        }, {
            "vss": 647304,
            "name": "OS processes",
            "tgid": 0,
            "parentID": 0,
            "memoryUsedPc": 0.18,
            "cpuUsedPc": 0.02,
            "id": 0,
            "rss": 22600
        }, {
            "vss": 3244792,
            "name": "RDS processes",
            "tgid": 0,
            "parentID": 0,
            "memoryUsedPc": 2.80,
            "cpuUsedPc": 0.78,
            "id": 0,
            "rss": 441652
        }]
    }
```

# Setup

1. Create a KMS key for the Datadog API key and app key
   - Create a KMS key. Refer to the [AWS KMS Creating Keys][1] documentation for step by step instructions.
   - Encrypt the token using the AWS CLI. `aws kms encrypt --key-id alias/<KMS key name> --plaintext '{"api_key":"<dd_api_key>", "app_key":"<dd_app_key>"}'`
   - Make sure to save the base-64 encoded, encrypted key (`CiphertextBlob`). This is used for the `KMS_ENCRYPTED_KEYS` variable in all lambda functions.
   - Optional: set the environment variable `DD_SITE` to `datadoghq.eu` to automatically forward data to your EU platform.

2. Create and configure a lambda function
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

   - Create a `lambda_execution` role and attach this policy.

   - Create a lambda function: skip the blueprint, name it `functionname`, set the runtime to `Python 2.7`, the handle to `lambda_function.lambda_handler`, and the role to `lambda_execution`.

   - Copy the content of `functionname/lambda_function.py` in the code section, and make sure to update the `KMS_ENCRYPTED_KEYS` environment variable with the encrypted key generated in step 1.

3. Subscribe to the appropriate log stream.


# How to update the zip file for the AWS Serverless Apps

1. After modifying the files that you want inside the respective lambda app directory, run:

```
aws cloudformation package --template-file rds-enhanced-sam-template.yaml --output-template-file rds-enhanced-serverless-output.yaml --s3-bucket BUCKET_NAME
```

[1]: http://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html
