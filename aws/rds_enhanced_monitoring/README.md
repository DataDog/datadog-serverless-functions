# RDS Enhanced Monitoring
Parses RDS Enhanced Monitoring logs to deliver OS-level metrics including CPU, memory, swap, disk I/O, network throughput, and per-process resource usage at up to 1-second granularity, providing visibility into database host performance that standard CloudWatch RDS metrics don't provide.  Metrics are sent to Datadog and queryable under the `aws.rds.*` metric namespace.

# Setup

## Prerequisites

Refer to [Enable RDS Enhanced Monitoring][1] to set up enhanced monitoring for your RDS hosts.

## 1. Encrypt Your Datadog API Key

It is strongly recommended to encrypt your Datadog API key. Choose one of the following options to do so. A plaintext key should only be used for non-production or testing environments.  See [Add an API key or client token][6] for help creating your Datadog API key.

### (a) AWS KMS

There are two supported KMS flows. They use different environment
variables and are not interchangeable.

   - API key only (recommended for new deployments)
      1. Refer to the [AWS KMS Creating Keys][2] documentation for step by step instructions on creating a key.
      2. Encrypt your API key using the AWS CLI.<br>
      `aws kms encrypt --key-id alias/<KMS_KEY_NAME> --plaintext '<DD_API_KEY>'`
      3. Keep the `CiphertextBlob` on hand for the next section.

   - API and APP key together (legacy)
      1. Encrypt a JSON blob containing both keys, with an `EncryptionContext` set to
         the exact name of the Lambda function you're deploying to. The context is
         required.  Decryption will fail if it doesn't match the function's name.
         ```
         aws kms encrypt \
           --key-id alias/<KMS_KEY_NAME> \
           --plaintext '{"api_key":"<DD_API_KEY>","app_key":"<DD_APP_KEY>"}' \
           --encryption-context LambdaFunctionName=<FUNCTION_NAME>
         ```
      2. Keep the `CiphertextBlob` on hand for the next section.  Use this option if you need to 
         supply both keys, or you're carrying over a value encrypted this way from an existing deployment.

### (b) AWS Secrets Manager
   1. Refer to the [AWS Secrets Manager Create a secret][4] documentation for step by step instructions on creating a secret.
   2. Create the secret using the AWS CLI.<br>
   `aws secretsmanager create-secret --name <SECRET_NAME> --secret-string '<DD_API_KEY>'`
   3. Keep the secret's `ARN` on hand for the next section.

### (c) AWS SSM
   1.  Refer to the [AWS Systems Manager Create a parameter][5] documentation for step by step instructions on creating a parameter.
   2.  Create the parameter using the AWS CLI.<br>
   `aws ssm put-parameter --name <PARAMETER_NAME> --value '<DD_API_KEY>' --type SecureString`
   3.  Keep the parameter's Name (or its full ARN, if it lives in a different region
       than the function) on hand for the next section.

**Note:** If the parameter is a `SecureString` encrypted with a customer-managed KMS key (rather than the default `alias/aws/ssm` key), you'll also need to grant `kms:Decrypt` on that key. If deploying via the SAR application, set the `KMSKeyId` parameter to that key's id, and the generated policy will cover it — see the note below.

### (d) Plaintext
**Note**: Plaintext is not recommended and should only be used for non-production or testing environments.
   1. In Datadog, go to **Organization Settings** --> **API Keys** and keep the value on hand for the next section.

## 2. Deploy the RDS Enhanced SAR Application
   1.  Sign into the AWS management console
   2.  Visit the [application overview page][3] and click Deploy.
   3.  Based on the encryption method you chose, fill out the matching stack parameter(s) and leave the rest blank. If your Datadog account uses a site other than US1, also set `DdSite` to match.
   4.  After filling out the stack parameter(s) click Deploy to launch the CloudFormation stack.

**(a) AWS KMS**<br>
Enter the KMS Key ID for `KMSKeyId` and either the encrypted `CiphertextBlob` containing your API key for `DdKmsApiKey` or the encrypted `CiphertextBlob` containing your API and APP key for `KmsEncryptedKeys`.

**(b) AWS Secrets Manager**<br>
Enter the Secret ARN for `DdApiKeySecretArn`.

**(c) AWS SSM**<br>
Enter the name of the SSM parameter or the ARN of the SSM parameter if it lives in a different region than the Lambda function for `DdApiKeySsmName`.  If you encrypted the SSM parameter with a customer-managed KMS key, you must also specify the KMS Key ID for  `KMSKeyId`.

**(d) Plaintext**<br>
Enter the plain API key for `DdApiKey`.

## 3. Subscribe the RDS Enhanced Lambda to the RDSOSMetrics log group

1. Sign into the AWS management console and open the **CloudWatch** service.
2. In the left navigation pane, click **Logs** --> **Logs Management**.
3. Select the **RDSOSMetrics** log group. RDS creates this log group automatically
   once Enhanced Monitoring is enabled on a database instance (see [Prerequisites](#prerequisites)).
4. Click **Actions** --> **Subscription filters** --> **Create Lambda subscription filter**.
5. Under **Choose destination**, select the
   RDS Enhanced Lambda function you deployed above.
6. Under **Configure log format and filters**, enter a name for the **Subscription filter** like
   `RDSEnhancedLogsFilter` but leave the **Subscription pattern**  blank so every log event is forwarded, then click **Start streaming**.

Once the subscription filter is created, the Lambda begins processing enhanced
monitoring events the next time RDS emits them and sends the metrics to Datadog.

## Manually Create the RDS Enhanced Lambda
If you want to create the Lambda without using the SAR application, follow these steps.

   1. Create a lambda function using **Author from scratch**, and give it a name like `DatadogRDSEnhanced`.  
       - Set the Runtime to `Python 3.12`
       - Set the Architecture to `arm64` 
       - Click **Create function**
   2. Copy the content from `lambda_function.py` in this repo to the code source for the Lambda.
   3. Add an environment variable for your API key based on the encryption method you chose.  If you use a Datadog site other than US1, create an environment variable `DD_SITE` and enter a [site parameter][7].
   4. Create a permissions policy granting the IAM permission required for your chosen credential option (see **Permission Policies** below), and attach it to the Lambda's execution role. Skip this step if a plaintext API key was used.
   5. [Subscribe the Lambda function to the RDSOSMetrics log group](#3-subscribe-the-rds-enhanced-lambda-to-the-rdsosmetrics-log-group).

**Environment Variables**

**(a) AWS KMS**<br>
Create an environment variable `DD_KMS_API_KEY` and enter the encrypted CiphertextBlob containing your API key.
If you encrypted both your API and APP key create an environment variable `KmsEncryptedKeys` and enter the encrypted CiphertextBlob.

**(b) AWS Secrets Manager**<br>
Create an environment variable `DD_API_KEY_SECRET_ARN` and enter the Secret ARN.

**(c) AWS SSM**<br>
Create an environment variable `DD_API_KEY_SSM_NAME` and enter the name of the SSM parameter or the ARN of the SSM parameter if it lives in a different region than the Lambda function.

**(d) Plaintext**<br>
Create an environment variable `DD_API_KEY` and enter the API key.

**Permission Policies**

**(a) AWS KMS or (c) AWS SSM with a customer-managed KMS key**
```json
{
    "Effect": "Allow",
    "Action": [
        "kms:Decrypt"
    ],
    "Resource": [
        "<KMS ARN>"
    ]
}
```

**(b) AWS Secrets Manager**
```json
{
    "Effect": "Allow",
    "Action": [
        "secretsmanager:GetSecretValue"
    ],
    "Resource": [
        "<Secret ARN>"
    ]
}
```

**(c) AWS SSM**
```json
{
    "Effect": "Allow",
    "Action": [
        "ssm:GetParameter"
    ],
    "Resource": [
        "<SSM Parameter ARN>"
    ]
}
```

# How to update the zip file for the AWS Serverless Apps

1. After modifying the files that you want inside the respective lambda app directory, run:

```
aws cloudformation package --template-file rds-enhanced-sam-template.yaml --output-template-file rds-enhanced-serverless-output.yaml --s3-bucket BUCKET_NAME
```

# RDS message example
<details>
    <summary>Click to expand</summary>

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
</details>

[1]: https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_Monitoring.OS.Enabling.html
[2]: http://docs.aws.amazon.com/kms/latest/developerguide/create-keys.html
[3]: https://serverlessrepo.aws.amazon.com/applications/arn:aws:serverlessrepo:us-east-1:464622532012:applications~Datadog-RDS-Enhanced
[4]: https://docs.aws.amazon.com/secretsmanager/latest/userguide/create_secret.html
[5]: https://docs.aws.amazon.com/systems-manager/latest/userguide/param-create-cli.html
[6]: https://docs.datadoghq.com/account_management/api-app-keys/#add-an-api-key-or-client-token
[7]: https://docs.datadoghq.com/getting_started/site/#access-the-datadog-site
