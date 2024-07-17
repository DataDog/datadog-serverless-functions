# Output the "list" of all subscribed regions.

output "all_availability_domains_in_your_tenancy" {
  value = data.oci_identity_region_subscriptions.subscriptions.region_subscriptions
}

output "tenancy_object_storage_namespace" {
  value = local.ocir_namespace
}

output "vcn_network_details" {
  depends_on  = [module.vcn]
  description = "Output of the created network infra"
  value = var.create_vcn ? {
    vcn_id             = module.vcn[0].vcn_id
    nat_gateway_id     = module.vcn[0].nat_gateway_id
    nat_route_id       = module.vcn[0].nat_route_id
    service_gateway_id = module.vcn[0].service_gateway_id
    sgw_route_id       = module.vcn[0].sgw_route_id
    subnet_id          = module.vcn[0].subnet_id[local.subnet]
    } : {
    vcn_id             = ""
    nat_gateway_id     = ""
    nat_route_id       = ""
    service_gateway_id = ""
    sgw_route_id       = ""
    subnet_id          = var.function_subnet_id
  }
}

output "function_application" {
  description = "OCID of the Function app"
  value       = oci_functions_application.metrics_function_app.id
}

output "function_application_function" {
  description = "OCID of the Function"
  value       = oci_functions_function.metrics_function.id
}

output "connector_hub" {
  description = "Connector hub created for forwarding the data to the function"
  value       = oci_sch_service_connector.metrics_service_connector.id
}
