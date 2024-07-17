resource "null_resource" "Login2OCIR" {
  count = local.user_image_provided ? 0 : 1
  provisioner "local-exec" {
    command = "echo '${var.oci_docker_password}' |  docker login ${local.oci_docker_repository} --username ${local.ocir_namespace}/${var.oci_docker_username} --password-stdin"
  }
}

### Repository in the Container Image Registry for the container images underpinning the function 
resource "oci_artifacts_container_repository" "function_repo" {
  # note: repository = store for all images versions of a specific container image - so it included the function name
  depends_on     = [null_resource.Login2OCIR]
  count          = local.user_image_provided ? 0 : 1
  compartment_id = var.compartment_ocid
  display_name   = local.ocir_repo_name
  is_public      = false
  defined_tags   = {}
  freeform_tags  = local.freeform_tags
}

# ### build the function into a container image and push that image to the repository in the OCI Container Image Registry
resource "null_resource" "FnImagePushToOCIR" {
  count      = local.user_image_provided ? 0 : 1
  depends_on = [oci_functions_application.metrics_function_app, null_resource.Login2OCIR]

  provisioner "local-exec" {
    command = "echo '${var.oci_docker_password}' |  docker login ${local.oci_docker_repository} --username ${local.ocir_namespace}/${var.oci_docker_username} --password-stdin"
  }

  # remove function image (if it exists) from local container registry
  provisioner "local-exec" {
    command     = "image=$(docker images | grep ${local.function_name} | awk -F ' ' '{print $3}') ; docker rmi -f $image &> /dev/null ; echo $image"
    working_dir = "metrics-function"
  }

  # build and tag the image from the docker file
  provisioner "local-exec" {
    command     = "docker build -t ${local.docker_image_path} . --no-cache"
    working_dir = "metrics-function"
  }

  # Push the docker image to the OCI registry
  provisioner "local-exec" {
    command     = "docker push ${local.docker_image_path}"
    working_dir = "metrics-function"
  }

  # remove function image (if it exists) from local container registry
  provisioner "local-exec" {
    command     = "docker rmi -f `docker images | grep ${local.function_name} | awk -F ' ' '{print $3}'`> /dev/null"
    working_dir = "metrics-function"
  }

}
