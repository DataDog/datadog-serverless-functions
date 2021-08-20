# Eventhub Log Forwarder Deployment

Powershell scripts to automatically create a 'log forwarding pipeline' using Azure EventHub to collect Azure Platform Logs.

At a high level, the scripts call Azure Powershell functions to create and deploy Azure resources, mostly defined via a URL to a json template.

The JSON template format is a [Azure Resource Manager (ARM)](https://docs.microsoft.com/en-us/azure/azure-resource-manager/templates/overview), which can store variables, define resources to create, dependencies... etc. And can be validated via e.g. a Visual Studio Code plugin mentioned therein (under Authoring tools). 

The exact steps these scripts automate are found in the ['Manual installation' of Log collection documentation](https://docs.datadoghq.com/integrations/azure/?tab=manualinstallation#log-collection).
