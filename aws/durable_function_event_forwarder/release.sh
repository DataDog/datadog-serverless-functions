#!/usr/bin/env bash

# Publishes the Lambda Durable Function event-forwarder CloudFormation template
# to the public Datadog CloudFormation template bucket:
#
#   https://datadog-cloudformation-template.s3.amazonaws.com/aws/lambda-durable-function-event-forwarder/<version>.yaml
#   https://datadog-cloudformation-template.s3.amazonaws.com/aws/lambda-durable-function-event-forwarder/latest.yaml
#
# The bucket lives in the Datadog Prod account (464622532012); the script
# authenticates with that account's prod-engineering role via aws-vault.
#
# Usage:
#   ./release.sh <version>          # e.g. ./release.sh 0.1.0
#
# A semantic version is REQUIRED. The script refuses to overwrite an existing
# <version>.yaml (immutable released versions); latest.yaml is always updated to
# point at the version being published.
#
# Override the aws-vault profile with AWS_VAULT_PROFILE if yours differs.

set -o nounset -o pipefail -o errexit

log_info() {
    local BLUE='\033[0;34m'
    local RESET='\033[0m'
    printf -- "%b%b%b\n" "${BLUE}" "${*}" "${RESET}" 1>&2
}

log_success() {
    local GREEN='\033[0;32m'
    local RESET='\033[0m'
    printf -- "%b%b%b\n" "${GREEN}" "${*}" "${RESET}" 1>&2
}

log_error() {
    local RED='\033[0;31m'
    local RESET='\033[0m'
    printf -- "%b%b%b\n" "${RED}" "${*}" "${RESET}" 1>&2
    exit 1
}

user_confirm() {
    local input
    read -r -p "${1:-Are you sure}? [y/N] " input </dev/tty
    case "${input}" in
    [yY][eE][sS] | [yY]) return 0 ;;
    *) return 1 ;;
    esac
}

# --- Configuration --------------------------------------------------------- #

# Datadog Prod account that owns the public template bucket.
readonly PROD_ACCOUNT_ID="464622532012"
readonly AWS_VAULT_PROFILE="${AWS_VAULT_PROFILE:-sso-prod-engineering}"

readonly BUCKET="datadog-cloudformation-template"
readonly KEY_PREFIX="aws/lambda-durable-function-event-forwarder"

# Template lives next to this script regardless of the caller's working dir.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TEMPLATE_PATH="${SCRIPT_DIR}/template.yaml"

# Run an AWS command as the Datadog Prod prod-engineering role.
aws_login() {
    aws-vault exec "${AWS_VAULT_PROFILE}" -- "$@"
}

# --- Pre-flight checks ----------------------------------------------------- #

if [[ ${#} -ne 1 ]]; then
    log_error "Usage: ${0} <version>   (e.g. ${0} 0.1.0)"
fi

VERSION="${1}"
if [[ ! ${VERSION} =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    log_error "You must use a semantic version (e.g. 0.1.0), got: '${VERSION}'"
fi

if ! command -v aws >/dev/null 2>&1; then
    log_error "aws CLI not found; please install it first"
fi

if ! command -v aws-vault >/dev/null 2>&1; then
    log_error "aws-vault not found; please install it first"
fi

if [[ ! -f ${TEMPLATE_PATH} ]]; then
    log_error "Template not found at ${TEMPLATE_PATH}"
fi

readonly VERSION_KEY="${KEY_PREFIX}/${VERSION}.yaml"
readonly LATEST_KEY="${KEY_PREFIX}/latest.yaml"
readonly VERSION_URL="https://${BUCKET}.s3.amazonaws.com/${VERSION_KEY}"
readonly LATEST_URL="https://${BUCKET}.s3.amazonaws.com/${LATEST_KEY}"

# --- Validate identity ----------------------------------------------------- #

log_info "Authenticating with aws-vault profile '${AWS_VAULT_PROFILE}'..."
CURRENT_ACCOUNT="$(aws_login aws sts get-caller-identity --query Account --output text)"

if [[ ${CURRENT_ACCOUNT} != "${PROD_ACCOUNT_ID}" ]]; then
    log_error "Expected to be in the Datadog Prod account (${PROD_ACCOUNT_ID}) but got ${CURRENT_ACCOUNT}. Check AWS_VAULT_PROFILE."
fi
log_success "Authenticated to account ${CURRENT_ACCOUNT}."

# --- Validate the template ------------------------------------------------- #
# Validate locally with cfn-lint rather than cloudformation:ValidateTemplate —
# the publishing role is scoped to S3 and is not granted CloudFormation
# actions. cfn-lint needs no AWS permissions.

if command -v cfn-lint >/dev/null 2>&1; then
    log_info "Validating ${TEMPLATE_PATH} with cfn-lint..."
    set +e
    cfn-lint "${TEMPLATE_PATH}"
    LINT_RC=$?
    set -e
    # cfn-lint exit codes are a bitmask: 2 = errors, 4 = warnings, 8 = info.
    # Only error-level findings should block a release.
    if ((LINT_RC & 2)); then
        log_error "cfn-lint reported errors; aborting."
    fi
    log_success "Template passed cfn-lint (no error-level findings)."
else
    log_info "cfn-lint not found; skipping local template validation."
fi

# --- Refuse to overwrite an already-published version ---------------------- #

log_info "Checking whether s3://${BUCKET}/${VERSION_KEY} already exists..."
if aws_login aws s3api head-object --bucket "${BUCKET}" --key "${VERSION_KEY}" >/dev/null 2>&1; then
    log_error "s3://${BUCKET}/${VERSION_KEY} already exists. Released versions are immutable; bump the version."
fi
log_success "Version ${VERSION} is not published yet."

# --- Confirm and publish --------------------------------------------------- #

log_info "About to publish:"
log_info "  ${TEMPLATE_PATH}"
log_info "    -> s3://${BUCKET}/${VERSION_KEY}   (new, immutable)"
log_info "    -> s3://${BUCKET}/${LATEST_KEY}    (overwrite: latest -> ${VERSION})"

if ! user_confirm "Continue"; then
    log_error "Aborting..."
fi

log_info "Uploading versioned template..."
aws_login aws s3 cp "${TEMPLATE_PATH}" "s3://${BUCKET}/${VERSION_KEY}" --content-type "text/yaml"

log_info "Updating latest.yaml..."
aws_login aws s3 cp "${TEMPLATE_PATH}" "s3://${BUCKET}/${LATEST_KEY}" --content-type "text/yaml"

log_success "Published version ${VERSION}!"
log_info "Versioned URL: ${VERSION_URL}"
log_info "Latest URL:    ${LATEST_URL}"
log_info ""
log_info "CloudFormation quick-create URL (latest):"
log_info "https://console.aws.amazon.com/cloudformation/home#/stacks/create/review?templateURL=${LATEST_URL}&stackName=datadog-durable-function-event-forwarder"
