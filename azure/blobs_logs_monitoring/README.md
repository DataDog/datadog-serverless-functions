# Datadog-Azure function

The Datadog-Azure function is used to forward Azure logs to Datadog from new blob files added in
a storage account. The function reads the file, plits lines on \n and sends each line as
a log entry to Datadog.

**This is currently in beta, instructions and code are subject to modifications.**

## Quick Start

The provided Node.js script must be deployed into your Azure Functions service. Follow the tutorial below to learn how to do so:

### 1. Create a new EventHub triggered function

- Expand your function application and click the `+` button next to `Functions`. If this is the first function in your function application, select `Custom function`. This displays the complete set of function templates.
- In the search field type `Blob` and choose `Blob Trigger`.
- Select the `Javascript` language in the right menu.
- Enter a name for the function.
- Select the path in the storage account where you want to read file from you want to pull logs from.
- Add the wanted `Storage account connection` or create a new one if you haven't have one already.

### 2. Provide the code

#### 2.1 Shared library

- Select your Function App and go to `Function app settings` and copy paste the content of [`host.json`](../host.json).
- Go to the `Platform features` and click on `Advanced tools (Kudu)` under the Development tools section
- In the menu bar, click on Tools > Zip Push Deploy
- Create a folder name `Shared` by clicking on the "+" next to `/wwwroot`
- Click on Shared, add a file name `client.js`, and copy paste the content of [shared/client.js](../shared/client.js) then save.

#### 2.2 Azure function

- Copy paste the code of the [Datadog-Azure function](./index.js).

## Parameters

- **API KEY**:

There are 2 possibilities to set your [Datadog's API key](https://app.datadoghq.com/account/settings#api):

1. Replace `<DATADOG_API_KEY>` in the code with your API Key value.
2. Set the value through the `DD_API_KEY` environment variable

- **Custom Tags**:

You have two options to add custom tags to your logs:

- Manually by editing the function code: Replace the `''` placeholder for the `DD_TAGS` variable by a comma separated list of tags
- Automatically with the `DD_TAGS` environment variable

Learn more about Datadog tagging in our main [Tagging documentation](https://docs.datadoghq.com/tagging/).
