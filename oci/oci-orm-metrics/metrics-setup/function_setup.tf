resource "null_resource" "Login2OCIR" {
  count = local.user_image_provided ? 0 : 1
  provisioner "local-exec" {
    command = "echo '${var.oci_docker_password}' |  docker login ${local.oci_docker_repository} --username ${local.ocir_namespace}/${var.oci_docker_username} --password-stdin"
  }
}

### Repository in the Container Image Registry for the container images underpinning the function 
# resource "oci_artifacts_container_repository" "function_repo" {
#   # note: repository = store for all images versions of a specific container image - so it included the function name
#   depends_on     = [null_resource.Login2OCIR]
#   count          = local.user_image_provided ? 0 : 1
#   compartment_id = oci_identity_compartment.datadog-compartment.id
#   display_name   = local.ocir_repo_name
#   is_public      = false
#   defined_tags   = {}
#   freeform_tags  = local.freeform_tags
# }

# ### build the function into a container image and push that image to the repository in the OCI Container Image Registry
resource "null_resource" "FnImagePushToOCIR" {
  count      = local.user_image_provided ? 0 : 1
  depends_on = [oci_functions_application.metrics_function_app, null_resource.Login2OCIR]

  # remove function image (if it exists) from local container registry
  provisioner "local-exec" {
    command     = "image=$(docker images | grep ${local.function_name} | awk -F ' ' '{print $3}') ; docker rmi -f $image &> /dev/null ; echo $image"
    working_dir = "metrics-function"
  }

  # pull the function image (if it exists) from the container registry
  provisioner "local-exec" {
    command     = "fn build --verbose"
    working_dir = "metrics-function"
  }

  # tag the container image with the proper name - based on the actual name of the function
  provisioner "local-exec" {
    command     = "image=$(docker images | grep ${local.function_name} | awk -F ' ' '{print $3}') ; docker tag $image ${local.docker_image_path}"
    working_dir = "metrics-function"
  }
  # create a container image based on fake-fun (hello world), tagged for the designated function name 
  provisioner "local-exec" {
    command     = "docker push ${local.docker_image_path}"
    working_dir = "metrics-function"
  }

  # remove function image (if it exists) from local container registry
  provisioner "local-exec" {
    command     = "image=$(docker images | grep ${local.function_name} | awk -F ' ' '{print $3}') ; docker rmi -f $image &> /dev/null ; echo $image"
    working_dir = "metrics-function"
  }

}
