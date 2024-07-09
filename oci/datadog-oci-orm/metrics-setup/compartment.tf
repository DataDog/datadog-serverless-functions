resource "oci_identity_compartment" "datadog-compartment" {
  provider = oci.home
  # Required
  compartment_id = var.compartment_ocid
  description    = "Compartment for Terraform resources."
  name           = var.datadog_compartment
  freeform_tags  = local.freeform_tags
  defined_tags   = {}
}
