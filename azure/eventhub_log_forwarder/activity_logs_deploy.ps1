Set-AzContext -SubscriptionId $SubscriptionId

$ResourceGroupName = If (Test-Path variable:ResourceGroupName) {$ResourceGroupName} Else {"datadog-log-forwarder-rg"}
$ResourceGroupLocation = If (Test-Path variable:ResourceGroupLocation) {$ResourceGroupLocation} Else {"westus2"}
$EventhubNamespace = If (Test-Path variable:EventhubNamespace) {$EventhubNamespace} Else {"datadog-eventhub-namespace"}
$EventhubName = If (Test-Path variable:EventhubName) {$EventhubName} Else {"datadog-eventhub"}
$FunctionAppName = If (Test-Path variable:FunctionAppName) {$FunctionAppName} Else {"datadog-functionapp"}
$FunctionName = If (Test-Path variable:FunctionName) {$FunctionName} Else {"datadog-function"}
$DiagnosticSettingName = If (Test-Path variable:DiagnosticSettingname) {$DiagnosticSettingname} Else {"datadog-activity-logs-diagnostic-setting"}
$Site = If (Test-Path variable:Site) {$Site} Else {"datadoghq.com"}

$code = (New-Object System.Net.WebClient).DownloadString("https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/activity_logs_monitoring/index.js")

try  {
    New-AzResourceGroup -Name $ResourceGroupName -Location $ResourceGroupLocation

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
        -site $Site `
        -Verbose `
        -ErrorAction Stop
}
catch {
    Write-Error "An error occurred while deploying parent template:"
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
}
catch {
    Write-Error "An error occurred while deploying diagnostic settings template:"
    Write-Error $_
}
