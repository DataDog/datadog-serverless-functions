# Datadog-Azure function (Beta)

The Datadog-Azure function is used to forward Azure logs to Datadog, including Activity and Diagnostic logs from EventHub.

**This is currently in beta, instructions and code are subject to modifications.**

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

- Copy paste the code of the [Datadog-Azure function](./index.js)
- In the `Integrate` part, `Event Hub Cardinality` must be set to `Many`.
- In the `Integrate` part,  set the `Event Parameter Name` to `eventHubMessages`

## Parameters

- **API KEY**:

There are 2 possibilities to set your [Datadog's API key](https://app.datadoghq.com/account/settings#api):

1. Replace `<DATADOG_API_KEY>` in the code with your API Key value.
2. Set the value through the `DD_API_KEY` environment variable

- **Custom Tags**:

You have two options to add custom tags to your logs:

- Manually by editing the function code: Replace the `<TAG_KEY>:<TAG_VALUE>` placeholder for the `DD_TAGS` variable by a comma separated list of tags
- Automatically with the `DD_TAGS` environment variable

Learn more about Datadog tagging in our main [Tagging documentation](https://docs.datadoghq.com/tagging/).
