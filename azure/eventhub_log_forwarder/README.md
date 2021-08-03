# Eventhub Log Forwarder Deployment

Powershell scripts to autoamtically create a 'log forwarding pipeline' using Azure EventHub to collect Azure Platform Logs.

At a high level, the scripts call Azure Powershell functions to create and deploy Azure resources, mostly defined via a URL to a json template.

The JSON template format is a [Azure Resource Manager (ARM)](https://docs.microsoft.com/en-us/azure/azure-resource-manager/templates/overview), which can store variables, define resources to create, dependencies... etc. And can be validated via e.g. a VS Code plugin. 

The exact steps these scripts automate are found in the ['Manual installation' of Log collection documentation](https://docs.datadoghq.com/integrations/azure/?tab=manualinstallation#log-collection).

# Contributions
## Setup
Install PowerShell for MacOS (it's pre-installed on Windows):

`brew install --cask powershell`

Launch PowerShell:

`pwsh`

Install [Pester](https://pester.dev/docs/quick-start) for unit-testing:

`Install-module -name Pester`

## Testing
Run Powershell unit-tests (from the `pwsh` shell):

`Invoke-Pester -Path ./azure/test/`


You can use the Azure cloud shell to run the actual deployments in the Powershell scripts.

If you need to modify the JSON templates, you can temporarily replace the `-TemplateUri` link with a secret [Github Gist](https://gist.github.com/) that you can modify on the fly, as the content cannot be locally hosted on the machine and must be accessible by the Azure platform.