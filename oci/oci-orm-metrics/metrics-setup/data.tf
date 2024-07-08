# Source from https://registry.terraform.io/providers/oracle/oci/latest/docs/data-sources/identity_region_subscriptions

data "oci_identity_region_subscriptions" "subscriptions" {
  # Required
  provider   = oci.home
  tenancy_id = var.tenancy_ocid
}

data "oci_objectstorage_namespace" "namespace" {
  provider       = oci.home
  compartment_id = var.tenancy_ocid
}

data "oci_identity_tenancy" "tenancy_metadata" {
  tenancy_id = var.tenancy_ocid
}

data "oci_core_subnet" "input_subnet" {
  depends_on = [module.vcn]
  #Required
  subnet_id = var.create_vcn ? module.vcn[0].subnet_id[local.subnet] : var.function_subnet_id
}
