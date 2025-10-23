# Datadog Lambda Forwarder Changelog

## v5.0.0 - BREAKING CHANGES

### Overview

Version 5.0.0 of the Datadog Lambda Forwarder introduces several breaking changes that remove deprecated features and improve log filtering behavior. This release introduces a new way to enrich logs with tags that will reduce AWS Lambda related cost (S3, KMS and Lambda).

### New Features

#### 1. Backend Storage Tag Enrichment

**Added:**

- New `DD_ENRICH_S3_TAGS` / `DdEnrichS3Tags` parameter (default: `true`)
- New `DD_ENRICH_CLOUDWATCH_TAGS` / `DdEnrichCloudwatchTags` parameter (default: `true`)
- These instruct the Datadog backend to automatically enrich logs with resource tags **after ingestion**
- New cloudwatch tags can appear on logs, check your Datadog log index configuration to ensure smooth transition.

**Benefits:**

- **Reduces forwarder cost** and execution time
- Provides the same tag enrichment as `DdFetchS3Tags` and `DdFetchLogGroupTags`
- Requires [Resource Collection](https://docs.datadoghq.com/integrations/amazon-web-services/#resource-collection) enabled in your AWS integration

**Deprecation Notice:**

- `DdFetchS3Tags` is now marked as **DEPRECATED** in favor of `DdEnrichS3Tags`
- `DdFetchLogGroupTags` is now marked as **DEPRECATED** in favor of `DdEnrichCloudwatchTags`
- `DD_FETCH_S3_TAGS` now defaults to `false` (previously `true`)

---

### Breaking Changes

#### 1. Changed Regex Matching Behavior for Log Filtering

**What Changed:**

- `IncludeAtMatch` / `INCLUDE_AT_MATCH` and `ExcludeAtMatch` / `EXCLUDE_AT_MATCH` regex patterns now match **only against the log message** itself
- Previously, these patterns matched against the **entire JSON-formatted log**

**Migration Required:**

- **Review and update filtering regex patterns**
- If your patterns relied on matching against JSON structure or metadata fields, they will need to be rewritten
- Example changes needed:
    - **Before (v4)**: `\"awsRegion\":\"us-east-1\"` (matched JSON with escaped quotes)
    - **After (v5)**: `"awsRegion":"us-east-1"` (matches the message content directly)
- Patterns that matched the `message` field content should continue to work with minimal changes

---

#### 2. Removed TCP Transport Support

**What Changed:**

- Removed the `DD_USE_TCP` / `DdUseTcp` environment variable and parameter
- Deleted the TCP client implementation
- All logs now **must** be sent via HTTP/HTTPS

**Migration Required:**

- Remove any configuration setting `DD_USE_TCP=true` or `DdUseTcp=true`
- The forwarder will now exclusively use HTTP protocol
- If you were using TCP with custom ports (10516), these configurations will be ignored
- The default HTTP endpoint is now `http-intake.logs.<DD_SITE>` on port 443

---

#### 3. Removed Deprecated PrivateLink Environment Variable

**What Changed:**

- Removed the `DD_USE_PRIVATE_LINK` / `DdUsePrivateLink` environment variable and parameter

**Migration Required:**

- Remove any configuration setting `DD_USE_PRIVATE_LINK=true`
- **AWS PrivateLink is still fully supported**, follow [PrivateLink documentation](https://docs.datadoghq.com/agent/guide/private-link/) for more information about the setup:
    1. Set up VPC endpoints for `api`, `http-logs.intake`, and `trace.agent` as documented
    2. Configure the forwarder with `DdUseVPC=true`
    3. Set `VPCSecurityGroupIds` and `VPCSubnetIds`

**Why This Changed:**

- The variable was previously deprecated but not removed from past versions.

---

### Upgrade Instructions

Follow Datadog's official [documentation](https://docs.datadoghq.com/logs/guide/forwarder/?tab=cloudformation#upgrade-to-a-new-version) for upgrading Lambda Forwarder.

#### Pre-Upgrade Checklist

1. **Verify that TCP transport is not used:**

    ```bash
    aws lambda get-function-configuration --function-name "<YOUR_FORWARDER>" --query 'Environment.Variables.DD_USE_TCP'
    ```

2. **Verify that deprecated PrivateLink variable is not used:**

    ```bash
    aws lambda get-function-configuration --function-name "<YOUR_FORWARDER>" --query 'Environment.Variables.DD_USE_PRIVATE_LINK'
    ```

3. **Review log filtering patterns:**
    - When using `IncludeAtMatch` or `ExcludeAtMatch`, test the patterns against log messages only
    - Remove any JSON escaping (e.g., `\"` → `"`)

#### Testing

After upgrading:

1. Verify logs are being forwarded to Datadog
2. Check that filtering rules still work as expected
3. Confirm tag enrichment is working (check logs in Datadog Explorer)
4. Monitor forwarder execution duration and errors in CloudWatch
