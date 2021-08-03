param (
    $SubscriptionId,
    $ApiKey,
    $EventhubNamespace,
    $ResourceGroupName = "datadog-log-forwarder-rg",
    $ResourceGroupLocation  = "westus2",
    $EventhubName = "datadog-eventhub",
    $FunctionAppName = "datadog-functionapp",
    $FunctionName = "datadog-function",
    $DiagnosticSettingName = "datadog-activity-logs-diagnostic-setting",
    $DatadogSite = "datadoghq.com",
    $Environment = "AzureCloud"
)


function Get-RandomChars {
    param ([int]$count)
    return ((Get-Random -Count $count -InputObject ([char[]]"abcdefghijklmnopqrstuvwxyz1234567890")) -join '')
}

if (-Not ($SubscriptionId -And $ApiKey)) { Throw "`SubscriptionId` and `ApiKey` are required." }
if (-Not $EventhubNamespace) {
    $EventhubNamespace = "datadog-eventhub-ns-" + (Get-RandomChars -count 7)
}

Set-AzContext -SubscriptionId $SubscriptionId

$code = (New-Object System.Net.WebClient).DownloadString("https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/activity_logs_monitoring/index.js")

New-AzResourceGroup -Name $ResourceGroupName -Location $ResourceGroupLocation

$environment = Get-AzEnvironment -Name $Environment
$endpointSuffix = $environment.StorageEndpointSuffix

try {
New-AzResourceGroupDeployment `
    -TemplateUri "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/eventhub_log_forwarder/parent_template.json" `
    -ResourceGroupName $ResourceGroupName `
    -functionCode $code `
    -apiKey $ApiKey `
    -location $ResourceGroupLocation `
    -eventhubNamespace $EventhubNamespace `
    -eventHubName $EventhubName `
    -functionAppName $FunctionAppName `
    -functionName $FunctionName `
    -datadogSite $DatadogSite `
    -endpointSuffix $endpointSuffix `
    -Verbose `
    -ErrorAction Stop
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
