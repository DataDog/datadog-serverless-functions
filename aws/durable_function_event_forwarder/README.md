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
  requests; Datadog's AWS integration auto-tags incoming logs from the
  EventBridge envelope (`source:lambda`, `service:lambda`,
  `region:<aws-region>`, `aws_account:<account-id>`,
  `sourcecategory:aws`) and from the Firehose ARN.
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
| `Statuses` | no | "" | EventBridge `detail.status` values to forward (uppercase, comma-delimited). Empty (the default) forwards **all** statuses — no status filter is added to the rule. |
| `FunctionArnFilter1` … `FunctionArnFilter5` | no | "" | Up to 5 independent function-ARN filters. Each accepts an **unqualified** function ARN or an EventBridge wildcard over one (for example `arn:aws:lambda:us-east-2:123456789012:function:my-durable-*`); do not add a version/alias suffix — `:*` is appended automatically. All five empty matches all functions in the region. See [Filtering multiple functions](#filtering-multiple-functions). |
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
envelope:

```json
{
  "version": "0",
  "id": "...",
  "detail-type": "Durable Execution Status Change",
  "source": "aws.lambda",
  "account": "123456789012",
  "time": "<ISO 8601 from EventBridge>",
  "region": "us-east-1",
  "resources": [],
  "detail": {
    "functionArn": "arn:aws:lambda:us-east-1:123456789012:function:my-fn:$LATEST",
    "executionName": "...",
    "executionStartTime": "<ISO 8601>",
    "executionEndTime":   "<ISO 8601>",
    "status": "TIMED_OUT"
  }
}
```

The stack itself does not attach metadata to the Firehose request.
Datadog's AWS integration auto-derives these tags from the envelope and
the Firehose ARN:

- `source:lambda` and `service:lambda` (from `source:aws.lambda`)
- `region:<aws-region>`
- `aws_account:<account-id>`
- `sourcecategory:aws`

Anything beyond these — a service override
(`service:my-orders-service`), `env`/`version`, custom tags, attribute
flattening, ARN qualifier stripping, timestamp parsing for relative-time
tooltips — is the Datadog log processing pipeline's responsibility (see
below). The stack intentionally exposes no service/env/version/tags
parameters: the Firehose intake can't carry them as proper facets, so
configure them in the pipeline instead.

### Datadog-side processing pipeline

Configure a Datadog logs processing pipeline (Logs → Configuration →
Pipelines → New Pipeline, filter `source:lambda` +
`@detail-type:"Durable Execution Status Change"`) with these
processors:

1. **Date Remapper** on `time` so EventBridge's `time` becomes the log's
   official date.
2. **Attribute Remapper** to flatten `detail.*` to top-level attributes —
   for example `detail.functionArn` → `function_arn`,
   `detail.executionName` → `lambda.durable_function.execution_name`,
   etc. (Use snake_case names so they match the rest of the Lambda
   namespace.)
3. **Grok / String Builder** to strip the `:<qualifier>` suffix
   (`:$LATEST`, `:prod`, `:1`, …) from `function_arn`, so all events for
   the same function share a single ARN value regardless of how it was
   invoked.
4. **Arithmetic Processor** on `detail.executionStartTime` /
   `detail.executionEndTime` (parse to epoch ms) if you want numeric
   range facets and the relative-time tooltip on those fields.
5. **Message Remapper** if you want a human-readable message like
   `Durable execution <name> is <status>`.

These are all UI-configurable; no template changes needed. The benefit
of doing this in Datadog rather than in a transformer Lambda is that
pipeline tweaks ship instantly without redeploying the stack, and you
get to test against a sample log via Datadog's pipeline preview.

## Publishing the template (Datadog operators)

Once the template is hosted at a public S3 URL, customers can reference it
directly — no zip artifact, region replication, or layer publish is needed.
The template is the only thing to ship.

Publishing `template.yaml` to the public `datadog-cloudformation-template`
bucket is handled by separate release tooling, not by this PR. The published
keys are:

- `aws/lambda-durable-function-event-forwarder/<version>.yaml` (immutable;
  recommended for nested stacks)
- `aws/lambda-durable-function-event-forwarder/latest.yaml` (floating pointer,
  always updated to the latest published version)

Customer-facing URLs after publish:

- Versioned (recommended for nested stacks):
  `https://datadog-cloudformation-template.s3.amazonaws.com/aws/lambda-durable-function-event-forwarder/<version>.yaml`
- Latest (convenient for one-off console deploys; not pinned, will change):
  `https://datadog-cloudformation-template.s3.amazonaws.com/aws/lambda-durable-function-event-forwarder/latest.yaml`

### Quick-create link (give this to customers)

Drop the URL into a CloudFormation quick-create deeplink so customers can
launch the stack with one click. Anything not pre-filled defaults to the
parameter's `Default:` value.

```
https://console.aws.amazon.com/cloudformation/home#/stacks/quickcreate
  ?stackName=datadog-durable-function-event-forwarder
  &templateURL=https://datadog-cloudformation-template.s3.amazonaws.com/aws/lambda-durable-function-event-forwarder/latest.yaml
```

(Removed the line breaks — paste as a single URL.) The customer fills in
the API key parameter on the console form; never pre-fill `DdApiKey` in a
link.

## Deploying directly

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name datadog-durable-function-event-forwarder \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    DdApiKeySecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:datadog/api-key-AbCdEf
```

## Consuming as a nested stack

```yaml
DurableFunctionEvents:
  Type: AWS::CloudFormation::Stack
  Properties:
    TemplateURL: https://datadog-cloudformation-template.s3.amazonaws.com/aws/lambda-durable-function-event-forwarder/<version>.yaml
    Parameters:
      DdApiKeySecretArn: !Ref DatadogApiKeySecret
```

The template is fully self-contained — no Lambda zip artifact, no region
replication, no `ZipCopier` custom resource. Firehose forwards
EventBridge records to Datadog directly; all reshaping happens in
Datadog's logs processing pipeline.

## Filtering multiple functions

Up to 5 independent function-ARN filters are exposed as separate
parameters (`FunctionArnFilter1` … `FunctionArnFilter5`). Each accepts an
**unqualified** function ARN or an EventBridge wildcard over one (for
example `arn:aws:lambda:us-east-2:123456789012:function:my-durable-*`);
scope by region and account by including them in the pattern. Each
populated slot contributes one matcher to the EventBridge rule: the
supplied ARN with `:*` appended. The durable-execution `detail.functionArn`
always carries a version/alias qualifier (per the AWS
[Monitoring durable functions](https://docs.aws.amazon.com/lambda/latest/dg/durable-monitoring.html#durable-monitoring-eventbridge)
docs), so `:*` is what matches — do not add a qualifier yourself. An
`AllowedPattern` rejects a trailing qualifier so a pasted qualified ARN
fails at deploy time rather than silently matching nothing. Empty slots
are stripped from the rendered list at deploy time, so leaving gaps (e.g.,
populating slots 1, 3, 5) is fine.

Why five separate parameters instead of one comma-separated list:
`AWS::Events::Rule.EventPattern` is typed `Json` (an arbitrary blob), so
CloudFormation does not auto-convert `Fn::ForEach` Map output to a list
the way it does for schema-typed list properties. The only ways to
build a dynamic-length list inside an `EventPattern` are (a) a
custom-resource macro, (b) `CommaDelimitedList` with `!Select` plus
inline comma-padding tricks repeated per slot, or (c) fixed N slots
exposed as individual parameters. We chose (c) because each slot is
locally simple to read in the template.

If you need more than 5 filters in one region, either widen one of the
slots with a wildcard (`...:function:prod-*` covers every function whose
name starts with `prod-`) or deploy a second stack — they're independent.

## Files

| File | Purpose |
| --- | --- |
| `template.yaml` | Canonical CloudFormation template. |

## Notes

- The function-ARN filter emits one `wildcard` pattern per value: the
  supplied unqualified ARN with `:*` appended. The event's
  `detail.functionArn` always carries a version/alias qualifier, so the
  `:*` is what matches; a bare-ARN matcher would never fire.
- `BufferingHints` is set explicitly even at its default value: omitting
  it has historically caused CloudFormation drift on subsequent updates.
- The backup bucket is retained on stack deletion
  (`DeletionPolicy: Retain`) so failed records survive teardown.
