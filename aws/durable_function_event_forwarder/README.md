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
| `DdApiKey` | one of four | "" | Plaintext Datadog API key (`NoEcho`). |
| `DdApiKeySecretArn` | one of four | "" | ARN of a Secrets Manager secret whose `SecretString` is the API key. Resolved via `{{resolve:secretsmanager:...}}`. |
| `DdApiKeySsmParameterName` | one of four | "" | Name of an SSM SecureString parameter holding the API key. Resolved via `{{resolve:ssm-secure:...}}`. |
| `DdApiKeyKmsCiphertext` | one of four | "" | Base64-encoded KMS ciphertext of the API key. A deploy-time Lambda decrypts it via `kms:Decrypt` and hands the plaintext to Firehose as a `NoEcho` custom-resource attribute. See [API key from KMS ciphertext](#api-key-from-kms-ciphertext). |
| `DdApiKeyKmsKeyArn` | when ciphertext set | "" | ARN of the KMS key that encrypted `DdApiKeyKmsCiphertext`. Used to scope the decrypter Lambda's `kms:Decrypt` permission. Required when `DdApiKeyKmsCiphertext` is set (enforced by a `Rules` assertion). |
| `DdSite` | no | `datadoghq.com` | Datadog site; used to build the Firehose destination URL. |
| `DdService` | no | `datadog-durable-function-event-forwarder` | Datadog `service` tag applied to every forwarded event. Override to match your existing service taxonomy. |
| `DdEnv` | no | "" | Datadog `env` tag. |
| `DdVersion` | no | "" | Datadog `version` tag. |
| `DdTags` | no | "" | Comma-delimited extra tags (for example `team:durable,owner:platform`). |
| `Statuses` | no | `TIMED_OUT,STOPPED` | EventBridge `detail.status` values to forward. Must be uppercase, comma-delimited. |
| `FunctionNameFilter1` … `FunctionNameFilter5` | no | "" | Up to 5 independent function-name filters. Each accepts a name or EventBridge wildcard (for example `prod-*-orders`). All five empty matches all functions in the region. Each populated slot adds matchers for both unqualified and version/alias-qualified ARNs — see [Filtering multiple functions](#filtering-multiple-functions). |
| `BufferIntervalSeconds` | no | `60` | Firehose buffer interval (60–900). |

`Rules.ApiKeyRequired` asserts at least one of the four API key parameters
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
below). The `DdService`/`DdEnv`/`DdVersion`/`DdTags` parameters remain
on the stack for forward compatibility but are not currently propagated;
configure their equivalents in the pipeline instead.

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

The convention mirrors `aws/logs_monitoring/release.sh` in this repo:

- **Public bucket**: `datadog-cloudformation-template` (same bucket the
  Lambda Forwarder already uses).
- **Versioned object key**:
  `aws/durable_function_event_forwarder/<version>.yaml`
- **Floating "latest" key**:
  `aws/durable_function_event_forwarder/latest.yaml`
- **Sandbox / staging**: separate path
  `aws/durable_function_event_forwarder-staging/<version>.yaml` against the
  per-environment sandbox bucket.

Upload commands per release (run from this directory):

```bash
VERSION=$(yq '.Mappings.Constants.DdDurableEventForwarder.Version' template.yaml | tr -d '"')
BUCKET=datadog-cloudformation-template

aws cloudformation validate-template --template-body file://template.yaml

aws s3 cp template.yaml \
  "s3://${BUCKET}/aws/durable_function_event_forwarder/${VERSION}.yaml" \
  --content-type "application/yaml"

aws s3 cp template.yaml \
  "s3://${BUCKET}/aws/durable_function_event_forwarder/latest.yaml" \
  --content-type "application/yaml"
```

Customer-facing URLs after publish:

- Versioned (recommended for nested stacks):
  `https://datadog-cloudformation-template.s3.amazonaws.com/aws/durable_function_event_forwarder/<version>.yaml`
- Latest (convenient for one-off console deploys; not pinned, will change):
  `https://datadog-cloudformation-template.s3.amazonaws.com/aws/durable_function_event_forwarder/latest.yaml`

### Quick-create link (give this to customers)

Drop the URL into a CloudFormation quick-create deeplink so customers can
launch the stack with one click. Anything not pre-filled defaults to the
parameter's `Default:` value.

```
https://console.aws.amazon.com/cloudformation/home#/stacks/quickcreate
  ?stackName=datadog-durable-function-event-forwarder
  &templateURL=https://datadog-cloudformation-template.s3.amazonaws.com/aws/durable_function_event_forwarder/latest.yaml
  &param_DdService=<service>
  &param_DdEnv=<env>
```

(Removed the line breaks — paste as a single URL.) The customer fills in
the API key parameter on the console form; never pre-fill `DdApiKey` in a
link.

### Release checklist

1. Bump `Mappings.Constants.DdDurableEventForwarder.Version` in
   `template.yaml`.
2. `aws cloudformation validate-template ...`
3. `aws s3 cp` to both `<version>.yaml` and `latest.yaml` keys.
4. Tag the release (`git tag durable-function-event-forwarder/<version>`).

A `release.sh` modeled on `aws/logs_monitoring/release.sh` can automate
steps 1–4. It is intentionally not committed yet — the template ships
self-contained, so a one-line `aws s3 cp` is sufficient until cross-env
sandbox/prod automation is needed.

## Deploying directly

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name datadog-durable-function-event-forwarder \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    DdApiKeySecretArn=arn:aws:secretsmanager:us-east-1:123456789012:secret:datadog/api-key-AbCdEf \
    DdService=my-service \
    DdEnv=prod
```

## Consuming as a nested stack

```yaml
DurableFunctionEvents:
  Type: AWS::CloudFormation::Stack
  Properties:
    TemplateURL: https://<datadog-published-templates-bucket>/aws/durable_function_event_forwarder/<version>/template.yaml
    Parameters:
      DdApiKeySecretArn: !Ref DatadogApiKeySecret
      DdService: my-service
      DdEnv: prod
```

The template is fully self-contained — no Lambda zip artifact, no region
replication, no `ZipCopier` custom resource. Firehose forwards
EventBridge records to Datadog directly; all reshaping happens in
Datadog's logs processing pipeline.

## Filtering multiple functions

Up to 5 independent function-name filters are exposed as separate
parameters (`FunctionNameFilter1` … `FunctionNameFilter5`). Each
populated slot contributes two matchers to the EventBridge rule — one
for unqualified ARNs and one for version/alias-qualified ARNs. Empty
slots are stripped from the rendered list at deploy time, so leaving
gaps (e.g., populating slots 1, 3, 5) is fine.

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
slots with a wildcard (`prod-*` covers every function starting with
`prod-`) or deploy a second stack — they're independent.

## API key from KMS ciphertext

`DdApiKeyKmsCiphertext` accepts the base64 output of:

```bash
aws kms encrypt \
  --key-id arn:aws:kms:us-east-1:123456789012:key/abcd... \
  --plaintext "$DATADOG_API_KEY" \
  --query CiphertextBlob \
  --output text
```

At stack create/update time, a short-lived Lambda decrypts the ciphertext
once via `kms:Decrypt` and returns the plaintext to CloudFormation as a
`NoEcho` custom-resource attribute. The Firehose `AccessKey` then
references the value via `!GetAtt DecryptedApiKey.ApiKey`.

The decrypter Lambda's IAM role is scoped to `kms:Decrypt` on the single
key ARN you pass as `DdApiKeyKmsKeyArn`. A `Rules` assertion fails the
stack action if the ciphertext is set without the key ARN.

**Security trade-off.** The plaintext is materialized in two places
during deploy: the custom-resource response body (suppressed from stack
events by `NoEcho: true`) and the rendered Firehose resource properties.
This is weaker than `DdApiKeySecretArn` or `DdApiKeySsmParameterName`,
which AWS treats specially and never logs. Use the KMS-ciphertext option
when you already have an encrypted ciphertext blob in your deployment
flow (e.g., from `serverless-plugin-kms` or an internal config store)
and don't want to add a Secrets Manager / SSM secret.

The decrypter resources (`ApiKeyKmsDecrypterFunction`,
`ApiKeyKmsDecrypterRole`, `ApiKeyKmsDecrypterLogGroup`, `DecryptedApiKey`)
are conditional on `UseApiKeyKms` and only exist when
`DdApiKeyKmsCiphertext` is set — no overhead for the other three API-key
methods.

## Files

| File | Purpose |
| --- | --- |
| `template.yaml` | Canonical CloudFormation template. |

## Notes

- The function-name filter emits two `wildcard` patterns per value so it
  matches both unqualified ARNs and version/alias-qualified ARNs. A single
  `suffix(":function:<name>")` matcher would miss qualified ARNs.
- `BufferingHints` is set explicitly even at its default value: omitting
  it has historically caused CloudFormation drift on subsequent updates.
- The backup bucket is retained on stack deletion
  (`DeletionPolicy: Retain`) so failed records survive teardown.
