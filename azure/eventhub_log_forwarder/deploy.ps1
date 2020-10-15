param
(
    $ResourceGroupName,
    $ResourceGroupLocation,
    $ApiKey,
    $EventhubNamespace = "datadog-eventhub-namespace",
    $EventhubName = "datadog-eventhub",
    $FunctionAppName = "datadog-functionapp",
    $FunctionName = "datadog-function",
    $DiagnosticSettingname = "datadog-activity-logs-diagnostic-setting-2"
)

$parentTemplateURI = "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/eventhub_log_forwarder/parent_template.json"
$diagnosticSettingsTemplateURI = "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/eventhub_log_forwarder/activity_log_diagnostic_settings.json"
$codePath = "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/activity_logs_monitoring/index.js"

# since function templates require the files and code are inline in the template we have to pass this as a parameter
# this line downloads the code as a string from the master branch on github.
$code = (New-Object System.Net.WebClient).DownloadString($codePath)

try  {
# create resource group
New-AzResourceGroup -Name $ResourceGroupName -Location $ResourceGroupLocation

# template parameters for parent template
$templateParameters = @{}
$templateParameters.Add("functionCode", $code)
$templateParameters.Add("apiKey", $apiKey)
$templateParameters.Add("location", $ResourceGroupLocation)
$templateParameters.Add("eventhubNamespace", $EventhubNamespace)
$templateParameters.Add("eventHubName", $EventhubName)
$templateParameters.Add("functionAppName", $FunctionAppName)
$templateParameters.Add("functionName", $FunctionName)

# deploy the parent template
New-AzResourceGroupDeployment `
    -TemplateUri $parentTemplateURI `
    -ResourceGroupName $ResourceGroupName `
    -TemplateParameterObject $templateParameters `
    -Verbose `
    -ErrorAction Stop

}
catch {
    Write-Error "An error occurred while deploying parent template:"
    Write-Error $_
    Return
}

# template parameters for activity log diagnostic settings

try {

$diagnosticSettingParameters = @{}
$diagnosticSettingParameters.Add("eventHubNamespace", $EventhubNamespace)
$diagnosticSettingParameters.Add("eventHubName", $EventhubName)
$diagnosticSettingParameters.Add("settingName", $DiagnosticSettingname)
$diagnosticSettingParameters.Add("resourceGroup", $ResourceGroupName)

# deploy the activity logs diagnostic settings, this needs to be deployed separately since it is not specific to the
# resource group
New-AzDeployment `
    -TemplateUri $diagnosticSettingsTemplateURI `
    -TemplateParameterObject $diagnosticSettingParameters `
    -Location $ResourceGroupLocation `
    -Verbose `
    -ErrorAction Stop
}
catch {
    Write-Error "An error occurred while deploying diagnostic settings template:"
    Write-Error $_
}