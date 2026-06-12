# Datadog Lambda Durable Function Event Forwarder

A self-contained CloudFormation template that captures AWS Lambda Durable
Function execution status change events and delivers them to the Datadog
HTTP intake via Amazon Data Firehose. Records arrive at Datadog as the
raw EventBridge envelope; any reshaping (field renaming, ARN qualifier
stripping, timestamp parsing) is configured on the Datadog side via a
logs processing pipeline.

## Architecture

```
EventBridge rule  ->  Firehose  ->  Datadog HTTP intake (raw EventBridge JSON)
                              \
                               -> S3 backup bucket (failed records only)
```

- The EventBridge rule subscribes to `aws.lambda` source events with
  detail-type `Durable Execution Status Change` and routes them to
  Firehose.
- Firehose forwards each record unchanged to
  `https://aws-kinesis-http-intake.logs.<DdSite>/v1/input` using the
  Datadog API key as the `X-Amz-Firehose-Access-Key` header. The stack
  does **not** attach any custom metadata to Firehose's outbound
  requests; tagging and reshaping are handled on the Datadog side.
- Records the endpoint rejects are written to the S3 backup bucket
  (`S3BackupMode: FailedDataOnly`); under normal operation the bucket
  stays empty.

## Parameters

| Parameter | Required | Default | Description |
| --- | --- | --- | --- |
| `DdApiKey` | one of three | "" | Plaintext Datadog API key (`NoEcho`). |
| `DdApiKeySecretArn` | one of three | "" | ARN of a Secrets Manager secret whose `SecretString` is the API key. Resolved via `{{resolve:secretsmanager:...}}`. |
| `DdApiKeySsmParameterName` | one of three | "" | Name of an SSM SecureString parameter holding the API key. Resolved via `{{resolve:ssm-secure:...}}`. |
| `DdSite` | no | `datadoghq.com` | Datadog site; used to build the Firehose destination URL. |
| `Statuses` | no | "" | EventBridge `detail.status` values to forward (uppercase, comma-delimited). Empty (the default) forwards **all** statuses. |
| `FunctionArnFilter1` … `FunctionArnFilter5` | no | "" | Up to 5 independent function-ARN filters. Each accepts an **unqualified** function ARN or an EventBridge wildcard over one (for example `arn:aws:lambda:us-east-2:123456789012:function:my-durable-*`); do not add a version/alias suffix — `:*` is appended automatically. All five empty matches all functions in the region. |
| `BufferIntervalSeconds` | no | `60` | Firehose buffer interval (60–900). |

`Rules.ApiKeyRequired` asserts at least one of the three API key parameters
is set and fails the stack action with a clear message otherwise.

## Outputs

| Output | Description |
| --- | --- |
| `DeliveryStreamArn` | Firehose delivery stream ARN. |
| `BackupBucketName` | S3 bucket name for failed records. |
| `EventRuleArn` | EventBridge rule ARN. |
| `ForwarderVersion` | Template version (from `Mappings.Constants`). |

## Forwarded log shape

The stack does **no transformation in AWS**. Firehose forwards each
EventBridge record to Datadog verbatim, so Datadog receives the raw
envelope. See AWS's
[Monitoring durable functions](https://docs.aws.amazon.com/lambda/latest/dg/durable-monitoring.html#durable-monitoring-eventbridge)
for the full event schema and the five `status` values (`RUNNING`,
`SUCCEEDED`, `FAILED`, `TIMED_OUT`, `STOPPED`):

```json
{
  "version": "0",
  "id": "d019b03c-a8a3-9d58-85de-241e96206538",
  "detail-type": "Durable Execution Status Change",
  "source": "aws.lambda",
  "account": "123456789012",
  "time": "2025-11-20T13:08:22Z",
  "region": "us-east-1",
  "resources": [],
  "detail": {
    "durableExecutionArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function:$LATEST/durable-execution/090c4189-b18b-4296-9d0c-cfd01dc3a122/9f7d84c9-ea3d-3ffc-b3e5-5ec51c34ffc9",
    "durableExecutionName": "order-123",
    "functionArn": "arn:aws:lambda:us-east-1:123456789012:function:my-function:2",
    "status": "RUNNING",
    "startTimestamp": "2025-11-20T13:08:22.345Z"
  }
}
```

Terminal states (`SUCCEEDED`, `STOPPED`, `FAILED`, `TIMED_OUT`) also include
an `endTimestamp`.

### Datadog-side processing pipeline

Install the **AWS Lambda** integration in Datadog; its out-of-the-box logs
pipeline is provisioned automatically and reshapes these events (field
renaming, ARN qualifier stripping, timestamp parsing, human-readable
message). No manual pipeline setup is required.
