param (
    $SubscriptionId,
    $ApiKey,
    $EventhubNamespace,
    $ResourceGroupLocation  = "westus2",
    $ResourceGroupName = "datadog-log-forwarder-rg-" + $ResourceGroupLocation,
    $EventhubName = "datadog-eventhub-" + $ResourceGroupLocation,
    $FunctionAppName = "datadog-functionapp-" + $ResourceGroupLocation,
    $FunctionName = "datadog-function-" + $ResourceGroupLocation,
    $DatadogSite = "datadoghq.com",
    $Environment = "AzureCloud"
)

function Get-RandomChars {
    param ([int]$count)
    return ((Get-Random -Count $count -InputObject ([char[]]"abcdefghijklmnopqrstuvwxyz1234567890")) -join '')
}

if (-Not ($SubscriptionId -And $ApiKey)) { Throw "`SubscriptionId` and `ApiKey` are required." }
if (-Not $EventhubNamespace) {
    $EventhubNamespace = "datadog-eventhub-ns-" + $ResourceGroupLocation + "-" + (Get-RandomChars -count 7)
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
