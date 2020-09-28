param
(
    $ResourceGroupName,
    $ResourceGroupLocation,
    $apiKey
)


$templateURI = "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/eventhub_log_forwarder/function_template.json"
$codePath = "https://raw.githubusercontent.com/DataDog/datadog-serverless-functions/master/azure/activity_logs_monitoring/index.js"

$code = (New-Object System.Net.WebClient).DownloadString($codePath)


# Read the contents of the function file and assemble deployment parameters
#$functionFileContents = [System.IO.File]::ReadAllText($FunctionFilePath)
$templateParameters = @{}
$templateParameters.Add("functionCode", $code)
$templateParameters.Add("apiKey", $apiKey)

New-AzResourceGroup -Name $resourceGroupName -Location $location

# Deploy the ARM template
New-AzureRmResourceGroupDeployment `
    -TemplateURI $templateURI `
    -ResourceGroupName $ResourceGroupName `
    -TemplateParameterObject $templateParameters `
    -Verbose

# New-AzResourceGroupDeployment -ResourceGroupName $resourceGroupName -TemplateFile $templateFile -functionCode $code -apiKey