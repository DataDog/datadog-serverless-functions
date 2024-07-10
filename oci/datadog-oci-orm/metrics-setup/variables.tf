variable "datadog_compartment" {
  type        = string
  description = "The name of the compartment created to hold all of the resources"
  default     = "datadog-metrics"
}

variable "create_vcn" {
  type        = bool
  default     = true
  description = "Optional variable to create virtual network for the setup. True by default"
}

variable "datadog_api_key" {
  type        = string
  description = "The API key for sending message to datadog endpoints"
}

variable "function_subnet_id" {
  type        = string
  default     = ""
  description = "The OCID of the subnet to be used for the function app. Required if not creating the VCN"
}

variable "function_image_path" {
  type        = string
  default     = ""
  description = "The full path of the function image. The image should be present in the container registry for the region"
}
variable "function_app_shape" {
  type        = string
  default     = "GENERIC_ARM"
  description = "The shape of the function application. The docker image should be built accordingly. Use ARM if using Oracle Resource managaer stack"
  validation {
    condition     = contains(["GENERIC_ARM", "GENERIC_X86", "GENERIC_X86_ARM"], var.function_app_shape)
    error_message = "Valid values are: GENERIC_ARM, GENERIC_X86, GENERIC_X86_ARM."
  }
}

variable "datadog_environment" {
  type        = string
  description = "The endpoint to hit for sending the metrics. Varies by different datacenter"
  validation {
    condition = contains(["ocimetrics-intake.datadoghq.com", "ocimetrics-intake.us5.datadoghq.com", "ocimetrics-intake.us3.datadoghq.com",
    "ocimetrics-intake.datadoghq.eu", "ocimetrics-intake.ap1.datadoghq.com", "ocimetrics-intake.ddog-gov.com"], var.datadog_environment)
    error_message = "Valid values for var: datadog_environment are (ocimetrics-intake.datadoghq.com, ocimetrics-intake.us5.datadoghq.com, ocimetrics-intake.us3.datadoghq.com, ocimetrics-intake.datadoghq.eu, ocimetrics-intake.ap1.datadoghq.com, ocimetrics-intake.ddog-gov.com)."
  }
}

variable "oci_docker_username" {
  type        = string
  default     = ""
  sensitive   = true
  description = "The docker login username for the OCI container registry. Used in creating function image. Not required if the image is already exists."
}

variable "oci_docker_password" {
  type        = string
  default     = ""
  sensitive   = true
  description = "The auth password for docker login to OCI container registry. Used in creating function image. Not required if the image already exists."
}

variable "service_connector_target_batch_size_in_kbs" {
  type        = string
  description = "The batch size (in Kb) in which to send payload to target"
  default     = "5000"
}

#*************************************
#         TF auth Requirements
#*************************************
variable "tenancy_ocid" {
  type        = string
  description = "OCI tenant OCID, more details can be found at https://docs.cloud.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm#five"
}
variable "region" {
  type        = string
  description = "OCI Region as documented at https://docs.cloud.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm"
}
variable "compartment_ocid" {
  type        = string
  description = "The compartment OCID to deploy resources to"
}

#*************************************
#         TF auth Requirements for CLI
#*************************************

# variable "user_ocid" {
#   type        = string
#   description = "The OCID of the user used in authentication and provisioning the resources"
# }
# variable "fingerprint" {
#   type        = string
#   description = "The user public key fingerprint"
# }
# variable "private_key_path" {
#   type        = string
#   description = "The path to the user private key"
# }
