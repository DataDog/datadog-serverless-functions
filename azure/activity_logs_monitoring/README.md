# Azure functions (Private Beta)

Function used to forward Azure logs, including Activity and Diagnostic logs from EventHub.
This is currently in Private beta, instructions and code are subject to modifications.

# Quick Start

The provided NodeJs script must be deployed into your Azure Functions service. We will explain how in this step-by-step tutorial.

## 1. Create a new EventHub triggered function

- Expand your function app and click the + button next to Functions. If this is the first function in your function app, select Custom function. This displays the complete set of function templates.
- In the search field type `Event Hub` and choose `Event Hub Trigger`
- Select the `Javascript` language in the right menu
- Enter a name for the function
- Add the wanted `Event Hub connection` or create a new one if you haven't have one already
- Select the `Event Hub consumer group` and the `Event Hub Name` you want to pull logs from

## 2. Provide the code

- Copy paste the code of the function
- In the `Integrate` part, make sure the `Event Hub Cardinality` is set to `Many`

## Parameters

- **API KEY**:

There are 2 possibilities to set your Datadog's API key (available in your Datadog platform):

1. Replace `<your-api-key>` in the code with the API Key value
2. Set the value through the `DD_API_KEY` environment variable

- **Custom Tags**:

You have two options to add custom tags to your logs (tags must be a comma-separated list of strings):

- Manually by editing the function code to add the tag list to the variable `DD_TAGS`
- Automatically with the `DD_TAGS` environment variable
