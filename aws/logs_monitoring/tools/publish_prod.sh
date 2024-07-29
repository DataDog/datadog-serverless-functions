#!/usr/bin/env bash

# Use with `./publish_prod.sh <DESIRED_NEW_VERSION>

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

# Ensure on main, and pull the latest
if [[ $(git rev-parse --abbrev-ref HEAD) != "master" ]]; then
    log_error "Not on master, aborting"
fi

# Ensure no uncommitted changes
if ! git diff --quiet; then
    log_error "Detected uncommitted changes, aborting"
fi

# Read the new version
if [[ -z ${1:-} ]]; then
    log_error "Must specify a layer version"
fi

LAYER_VERSION=$1

# Read the new version
if [[ -z ${2:-} ]]; then
    log_error "Must specify a forwarder version"
fi

FORWARDER_VERSION=$2

# Ensure AWS access before proceeding
aws-vault exec sso-govcloud-us1-fed-engineering -- aws sts get-caller-identity
aws-vault exec sso-prod-engineering -- aws sts get-caller-identity

log_info "Publishing layers to GovCloud AWS regions"
LAYER_VERSION="${LAYER_VERSION}" FORWARDER_VERSION"=${FORWARDER_VERSION}" aws-vault exec sso-govcloud-us1-fed-engineering -- ./tools/publish_layers.sh

log_info "Publishing layers to commercial AWS regions"
LAYER_VERSION="${LAYER_VERSION}" FORWARDER_VERSION"=${FORWARDER_VERSION}" aws-vault exec sso-prod-engineering -- ./tools/publish_layers.sh
