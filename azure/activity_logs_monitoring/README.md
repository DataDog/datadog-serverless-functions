# Datadog-Azure function

The Datadog-Azure function is used to forward Azure logs to Datadog, including Activity and Diagnostic logs from EventHub.

## Quick Start

The provided Node.js script must be deployed into your Azure Functions service. Follow the tutorial below to learn how to do so:

### 1. Create a new EventHub triggered function

- Expand your function application and click the `+` button next to `Functions`. If this is the first function in your function application, select `Custom function`. This displays the complete set of function templates.
- In the search field type `Event Hub` and choose `Event Hub Trigger`.
- Select the `Javascript` language in the right menu.
- Enter a name for the function.
- Add the wanted `Event Hub connection` or create a new one if you haven't have one already.
- Select the `Event Hub consumer group` and the `Event Hub Name` you want to pull logs from.

### 2. Provide the code

- Copy paste the code of the [Datadog-Azure function](./index.js).
- In the `Integrate` part:
  - `Event Hub Cardinality` must be set to `Many`.
  - Set the `Event Parameter Name` to `eventHubMessages`.

## 3. (optional) Send logs to EU or to a proxy

### Send logs to EU

Set the environment variable `DD_SITE` to `datadoghq.eu` and logs are automatically forwarded to your EU platform.

## Parameters

- **API KEY**:

There are 2 possibilities to set your [Datadog's API key](https://app.datadoghq.com/organization-settings/api-keys):

1. Replace `<DATADOG_API_KEY>` in the code with your API Key value.
2. Set the value through the `DD_API_KEY` environment variable

- **Custom Tags**:

You have two options to add custom tags to your logs:

- Manually by editing the function code: Replace the `<TAG_KEY>:<TAG_VALUE>` placeholder for the `DD_TAGS` variable by a comma separated list of tags
- Automatically with the `DD_TAGS` environment variable

Learn more about Datadog tagging in our main [Tagging documentation](https://docs.datadoghq.com/tagging/).

## Customization

- **Scrubbing PII**

To scrub PII from your logs, uncomment the SCRUBBER_RULE_CONFIG code. If you'd like to scrub more than just emails and IP addresses, add your own config to this map in the format
```
{
    NAME: {
        pattern: <regex_pattern>,
        replacement: <string to replace matching text with>}
}
```

- **Log Splitting**

To split array-type fields in your logs into individual logs, you can add sections to the DD_LOG_SPLITTING_CONFIG map in the code or by setting the DD_LOG_SPLITTING_CONFIG env variable (which must be a json string in the same format).
This will create an attribute in your logs called "parsed_arrays", which contains the fields in the format of the original log with the split log value.

An example of an azure.datafactory use case is provided in the code and commented out. The format is as follows:
```
{
  source_type:
    paths: [list of [list of fields in the log payload to iterate through to find the one to split]],
    keep_original_log: bool, if you'd like to preserve the original log in addition to the split ones or not,
    preserve_fields: bool, whether or not to keep the original log fields in the new split logs
}
```
