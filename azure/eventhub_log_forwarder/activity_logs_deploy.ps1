param (
    $SubscriptionId,
    $ApiKey,
    $EventhubNamespace,
    $FunctionAppName,
    $ResourceGroupLocation  = "westus2",
    $ResourceGroupName = "datadog-log-forwarder-rg",
    $EventhubName = "datadog-eventhub",
    $FunctionName = "datadog-function",
    $DiagnosticSettingName = "datadog-activity-logs-diagnostic-setting",
    $DatadogSite = "datadoghq.com",
    $Environment = "AzureCloud",
    $DatadogTags = ""
)

if (-Not ($SubscriptionId -And $ApiKey)) { Throw "`SubscriptionId` and `ApiKey` are required." }

Set-AzContext -SubscriptionId $SubscriptionId

$code = (New-Object System.Net.WebClient).DownloadString("https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/activity_logs_monitoring/index.js")

New-AzResourceGroup -Name $ResourceGroupName -Location $ResourceGroupLocation

$environment = Get-AzEnvironment -Name $Environment
$endpointSuffix = $environment.StorageEndpointSuffix
$secureApiKey = ConvertTo-SecureString $ApiKey -AsPlainText -Force

$deploymentArgs = @{
    TemplateUri = "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/eventhub_log_forwarder/parent_template.json"
    ResourceGroupName = $ResourceGroupName
    functionCode = $code
    apiKey = $secureApiKey
    location = $ResourceGroupLocation
    eventHubName = $EventhubName
    functionName = $FunctionName
    datadogSite = $DatadogSite
    endpointSuffix = $endpointSuffix
    datadogTags = $DatadogTags
}

# Use values if parameters passed, otherwise we rely on the default value generated by the ARM template
if ($EventhubNamespace) { $deploymentArgs["eventhubNamespace"] = $EventhubNamespace }
if ($FunctionAppName) { $deploymentArgs["functionAppName"] = $FunctionAppName }

try {
    $output = New-AzResourceGroupDeployment @deploymentArgs -Verbose -ErrorAction Stop
    # Get the generated globally-unique eventhub namespace
    $EventhubNamespace = $output.Outputs.eventHubNamespace.Value
} catch {
    Write-Error $_
    Return
}

try {
    New-AzDeployment `
        -TemplateUri "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/eventhub_log_forwarder/activity_log_diagnostic_settings.json" `
        -eventHubNamespace $EventhubNamespace `
        -eventHubName $EventhubName `
        -settingName $DiagnosticSettingName `
        -resourceGroup $ResourceGroupName `
        -Location $ResourceGroupLocation `
        -Verbose `
        -ErrorAction Stop
} catch {
    Write-Error $_
    Return
}
