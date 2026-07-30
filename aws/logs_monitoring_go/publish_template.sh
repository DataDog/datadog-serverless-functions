#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

# Uploads the Go Forwarder CloudFormation template to the distribution bucket.
# Usage: [PROFILE=...] [BUCKET=...] ./publish_template.sh

set -o nounset -o pipefail -o errexit

log_info() {
    local BLUE='\033[0;34m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${BLUE}" "${*}" "${RESET}" 1>&2
}

log_error() {
    local RED='\033[0;31m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${RED}" "${*}" "${RESET}" 1>&2
    exit 1
}

PROFILE="${PROFILE:-sso-prod-lambda-admin}"
BUCKET="${BUCKET:-datadog-cloudformation-template}"
KEY="aws/forwarder-staging/latest.yaml"

cd "$(dirname "$0")"

log_info "Uploading template.yaml to s3://${BUCKET}/${KEY}..."
aws-vault exec "${PROFILE}" -- aws s3 cp template.yaml "s3://${BUCKET}/${KEY}"

log_info "Done. Uploaded s3://${BUCKET}/${KEY}"
