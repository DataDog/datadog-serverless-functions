locals {
  # Names for the network infra
  vcn_name        = "${var.resource_name_prefix}-vcn"
  nat_gateway     = "${local.vcn_name}-natgateway"
  service_gateway = "${local.vcn_name}-servicegateway"
  subnet          = "${local.vcn_name}-private-subnet"
}

locals {
  # Names for the service connector
  connector_name = "${var.resource_name_prefix}-connector"
}

locals {
  # Tags for the provisioned resource
  freeform_tags = {
    datadog-terraform = "true"
  }
}

locals {
  # Name for tenancy namespace, metadata and regions
  ocir_namespace = data.oci_objectstorage_namespace.namespace.namespace
  oci_regions = tomap({
    for reg in data.oci_identity_region_subscriptions.subscriptions.region_subscriptions :
    reg.region_name => reg
  })
  oci_region_key      = lower(local.oci_regions[var.region].region_key)
  tenancy_home_region = data.oci_identity_tenancy.tenancy_metadata.home_region_key
}

locals {
  # OCI docker repository
  oci_docker_repository = "${local.oci_region_key}.ocir.io/${local.ocir_namespace}"
  oci_docker_host       = "${local.oci_region_key}.ocir.io"
  ocir_repo_name        = "${var.resource_name_prefix}-functions"
  function_name         = "datadog-function-metrics"
  docker_image_path     = "${local.oci_docker_repository}/${local.ocir_repo_name}/${local.function_name}:latest"
  # custom_image_path     = "${local.oci_region_key}.ocir.io/${var.function_image_path}"
  custom_image_path   = var.function_image_path
  user_image_provided = length(var.function_image_path) > 0 ? true : false
}
