resource "oci_functions_application" "metrics_function_app" {
  depends_on     = [data.oci_core_subnet.input_subnet]
  compartment_id = var.compartment_ocid
  config = {
    "DD_API_KEY"     = var.datadog_api_key
    "DD_COMPRESS"    = "true"
    "DD_INTAKE_HOST" = var.datadog_environment
    "DD_INTAKE_LOGS" = "false"
    "DD_MAX_POOL"    = "20"
    "TENANCY_OCID"   = var.tenancy_ocid
  }
  defined_tags  = {}
  display_name  = "${var.resource_name_prefix}-function-app"
  freeform_tags = local.freeform_tags
  network_security_group_ids = [
  ]
  shape = var.function_app_shape
  subnet_ids = [
    data.oci_core_subnet.input_subnet.id,
  ]
}

resource "oci_functions_function" "metrics_function" {
  depends_on = [null_resource.FnImagePushToOCIR, oci_functions_application.metrics_function_app]
  #Required
  application_id = oci_functions_application.metrics_function_app.id
  display_name   = "${oci_functions_application.metrics_function_app.display_name}-metrics-function"
  memory_in_mbs  = "256"

  #Optional
  defined_tags  = {}
  freeform_tags = local.freeform_tags
  image         = local.user_image_provided ? local.custom_image_path : local.docker_image_path
}
