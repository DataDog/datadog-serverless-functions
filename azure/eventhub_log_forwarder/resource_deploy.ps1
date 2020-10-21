
{
If (Test-Path variable:SubscriptionId) {} Else {Write-Error "`$SubscriptionId` must be set"}
Set-AzContext -SubscriptionId $SubscriptionId
}
$ResourceGroupLocation = If (Test-Path variable:ResourceGroupLocation) {$ResourceGroupLocation} Else {"westus2"}
$ResourceGroupName = If (Test-Path variable:ResourceGroupName) {$ResourceGroupName} Else {"datadog-log-forwarder-rg" + $ResourceGroupLocation}
$EventhubNamespace = If (Test-Path variable:EventhubNamespace) {$EventhubNamespace} Else {"datadog-eventhub-namespace" + $ResourceGroupLocation}
$EventhubName = If (Test-Path variable:EventhubName) {$EventhubName} Else {"datadog-eventhub" + $ResourceGroupLocation}
$FunctionAppName = If (Test-Path variable:FunctionAppName) {$FunctionAppName} Else {"datadog-functionapp" + $ResourceGroupLocation}
$FunctionName = If (Test-Path variable:FunctionName) {$FunctionName} Else {"datadog-function" + $ResourceGroupLocation}
$DatadogSite = If (Test-Path variable:DatadogSite) {$DatadogSite} Else {"datadoghq.com"}

$code = (New-Object System.Net.WebClient).DownloadString("https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/activity_logs_monitoring/index.js")

If ($ResourceGroupName == "datadog-log-forwarder-rg" + $ResourceGroupLocation) {
    New-AzResourceGroup -Name $ResourceGroupName -Location $ResourceGroupLocation
}

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
    -Verbose
