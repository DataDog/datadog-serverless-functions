# Datadog-Azure function

The Datadog-Azure integration function is used to forward Azure logs to Datadog, including Activity and Diagnostic logs from EventHub.

## Quick Start

The provided Node.js script must be deployed into your Azure Functions service. Follow the tutorial below to learn how to do so:

### 1. Create a new EventHub triggered function

```
dotnet build extensions.csproj -o bin --no-incremental
zip -r datadog_logs.zip *
az functionapp deployment source config-zip  -g myResourceGroup -n <app_name> --src datadog_logs.zip
az resource invoke-action --resource-group myResourceGroup --action syncfunctiontriggers --name <app_name> --resource-type Microsoft.Web/sites
```
[1]

## 2. (optional) Send logs to EU or to a proxy

### Send logs to EU

Add the app setting `DD_SITE` and set to `datadoghq.eu` and logs are automatically forwarded to your EU platform.

## Parameters

- **API KEY**:

Set the [Datadog's API key](https://app.datadoghq.com/account/settings#api) value through the `DD_API_KEY` app setting

- **Custom Tags**:

Add custom tags to your logs with the `DD_TAGS` environment variable by a comma separated list of tags

Learn more about Datadog tagging in our main [Tagging documentation](https://docs.datadoghq.com/tagging/).

[1]: https://docs.microsoft.com/en-us/azure/azure-functions/deployment-zip-push#cli
