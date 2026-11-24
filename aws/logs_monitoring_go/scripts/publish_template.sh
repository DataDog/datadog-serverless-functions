#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

# Stamps a version into the CloudFormation template and uploads it to one
# bucket/key.
#
# Credentials are inherited from the parent process; this script contains no
# aws-vault logic, so it works both as a release step and standalone:
#
#   VERSION=6.0.0 \
#   BUCKET=datadog-cloudformation-template \
#   KEY=aws/forwarder/v6/latest.yaml \
#       aws-vault exec sso-prod-lambda-admin -- ./scripts/publish_template.sh
#
# Optional:
#   TEMPLATE_PATH  defaults to deployments/template.yaml

set -o nounset -o pipefail -o errexit

# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"

cd "$(dirname "$0")/.."

TEMPLATE_PATH="${TEMPLATE_PATH:-deployments/template.yaml}"

for required in VERSION BUCKET KEY; do
    if [[ -z ${!required:-} ]]; then
        log_error "${required} is required"
    fi
done

if [[ ! -f ${TEMPLATE_PATH} ]]; then
    log_error "Template not found: ${TEMPLATE_PATH}"
fi

if ! command -v yq >/dev/null 2>&1; then
    log_error "yq not found, please install it"
fi

if ! command -v aws >/dev/null 2>&1; then
    log_error "aws not found, please install the AWS CLI"
fi

if ! aws sts get-caller-identity --cli-connect-timeout 10 --cli-read-timeout 30 >/dev/null 2>&1; then
    log_error "Not authenticated. Wrap this call, e.g. aws-vault exec sso-prod-lambda-admin -- ${0}"
fi

tmp_template="$(mktemp)"
cleanup() {
    rm -f "${tmp_template}"
}
trap cleanup EXIT

cp "${TEMPLATE_PATH}" "${tmp_template}"
yq --inplace ".Mappings.Constants.DdForwarder.Version |= \"${VERSION}\"" "${tmp_template}"

log_info
log_info "Template: ${TEMPLATE_PATH}"
log_info "Version:  ${VERSION}"
log_info "Target:   s3://${BUCKET}/${KEY}"
log_info

if ! user_confirm "Publish this version-stamped template"; then
    log_error "Aborting"
fi

run_traced aws s3 cp "${tmp_template}" "s3://${BUCKET}/${KEY}" --content-type "application/x-yaml"

log_success "Published ${VERSION} to s3://${BUCKET}/${KEY}"
