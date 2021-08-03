BeforeAll{
   try {
      # Catch missing params exception (as it's a script that's auto-executed and not a module)
      Import-Module ./azure/eventhub_log_forwarder/resource_deploy.ps1
   } catch {}
}

Describe "Test generate default Eventhub namespace with random alphanumeric chars" {
   It "Test random name generated" {
      $ResourceGroupLocation  = "westus2"
      "datadog-eventhub-ns-" + $ResourceGroupLocation + "-" + (Get-RandomChars -count 7) |
         Should -match '^datadog-eventhub-ns-westus2-[a-z0-9]{7}$'
   }
}