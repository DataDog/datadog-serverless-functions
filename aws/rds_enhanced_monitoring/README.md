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
            "writeKbPS": 2301.6,
            "readIOsPS": 0.03,
            "await": 4.04,
            "readKbPS": 0.13,
            "rrqmPS": 0,
            "util": 0.2,
            "avgQueueLen": 0.11,
            "tps": 28.27,
            "readKb": 4,
            "device": "rdsdev",
            "writeKb": 69048,
            "avgReqSz": 162.86,
            "wrqmPS": 0,
            "writeIOsPS": 28.23
        },{
            "writeKbPS": 177.2,
            "readIOsPS": 0.03,
            "await": 1.52,
            "readKbPS": 0.13,
            "rrqmPS": 0,
            "util": 0.35,
            "avgQueueLen": 0.03,
            "tps": 25.67,
            "readKb": 4,
            "device": "filesystem",
            "writeKb": 5316,
            "avgReqSz": 13.82,
            "wrqmPS": 8.3,
            "writeIOsPS": 25.63
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
        "physicalDeviceIO": [{
            "writeKbPS": 583.6,
            "readIOsPS": 0,
            "await": 2.32,
            "readKbPS": 0,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.02,
            "tps": 9.9,
            "readKb": 0,
            "device": "nvme3n1",
            "writeKb": 17508,
            "avgReqSz": 117.9,
            "wrqmPS": 4.97,
            "writeIOsPS": 9.9
        }, {
            "writeKbPS": 575.07,
            "readIOsPS": 0,
            "await": 3.04,
            "readKbPS": 0,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.03,
            "tps": 9.47,
            "readKb": 0,
            "device": "nvme1n1",
            "writeKb": 17252,
            "avgReqSz": 121.49,
            "wrqmPS": 3.97,
            "writeIOsPS": 9.47
        }, {
            "writeKbPS": 567.33,
            "readIOsPS": 0.03,
            "await": 2.69,
            "readKbPS": 0.13,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.02,
            "tps": 9.47,
            "readKb": 4,
            "device": "nvme5n1",
            "writeKb": 17020,
            "avgReqSz": 119.89,
            "wrqmPS": 3.07,
            "writeIOsPS": 9.43
        }, {
            "writeKbPS": 576.53,
            "readIOsPS": 0,
            "await": 2.64,
            "readKbPS": 0,
            "rrqmPS": 0,
            "util": 0.09,
            "avgQueueLen": 0.02,
            "tps": 9.8,
            "readKb": 0,
            "device": "nvme2n1",
            "writeKb": 17296,
            "avgReqSz": 117.66,
            "wrqmPS": 3.9,
            "writeIOsPS": 9.8
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

#### Encrypt Your Datadog API Key

Before configuring your Lambda, first choose one of the following options to encrypt your Datadog API key.

a. **Recommended**: AWS KMS
   1. Refer to the [AWS KMS Creating Keys][1] documentation for step by step instructions on creating a key.
   2. Encrypt your API key using the AWS CLI.
   `aws kms encrypt --key-id alias/<KMS key name> --plaintext '<dd_api_key>'`
   3. Store the `CiphertextBlob` as the `DD_KMS_API_KEY` environment variable in the next section.

b. AWS Secrets Manager
   1. Create a plaintext secret in AWS Secrets Manager using your API key as the value
   2. Store the ARN of the secret as the `DD_API_KEY_SECRET_ARN` environment variable

c. AWS SSM
   1.  Create a parameter in AWS SSM using your API key as the value
   2.  Store the Name of the parameter as the `DD_API_KEY_SSM_NAME` environment variable

d. **Not Recommended**: Plaintext
   1. Set your API key in plaintext as the `DD_API_KEY` environment variable.
   2. This flow is insecure and not recommended for production use cases.

#### Create the Lambda Function

1. Create and configure a lambda function
   - In the AWS Console, create a `lambda_execution` policy, with the following policy. If
     you chose an option other than KMS above, substitute the KMS statement with the
     appropriate permission for the service you used.

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

   - Create a lambda function: skip the blueprint, name it `functionname`, set the Runtime to `Python 3.11`, the Architecture to `arm64`, the handle to `lambda_function.lambda_handler`, and the role to `lambda_execution`.

   - Copy the content of `functionname/lambda_function.py` in the code section

   - Set the relevant environment variable with the API key payload you generated in step 1.

   - If you use Datadog's EU platform, set the environment variable `DD_SITE` to `datadoghq.eu`

2. Subscribe to the appropriate log stream.

# How to update the zip file for the AWS Serverless Apps

1. After modifying the files that you want inside the respective lambda app directory, run:

```
aws cloudformation package --template-file rds-enhanced-sam-template.yaml --output-template-file rds-enhanced-serverless-output.yaml --s3-bucket BUCKET_NAME
```

[1]: http://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html
