#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

# Releases the V6 Datadog Forwarder as aws-dd-forwarder-<version>.zip.
#
# Usage: ./release.sh DESIRED_VERSION ACCOUNT[staging|prod]
#
# Environment:
#   OVERWRITE             "true" republishes over already-published S3 keys
#   REGIONS               space-separated region override
#   SKIP_REGIONS          space-separated regions to exclude; not treated as failures
#   BASE_BRANCH           branch the release is cut from
#   PROD_GITHUB_RESTART   "true" resumes a prod release after the version PR merged

set -o nounset -o pipefail -o errexit

# shellcheck source-path=SCRIPTDIR
# shellcheck source=tools/common.sh
source "$(dirname "$0")/tools/common.sh"

if [[ ${#} -ne 2 ]]; then
    log_error "Usage: ${0} DESIRED_VERSION ACCOUNT[staging|prod]"
fi

FORWARDER_VERSION="${1}"
ACCOUNT="${2}"

if [[ ! ${FORWARDER_VERSION} =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]]; then
    log_error "The version must use the format <major>.<minor>.<patch>[-prerelease], got '${FORWARDER_VERSION}'"
fi

case "${ACCOUNT}" in
prod)
    AWS_PROFILE_NAME="sso-prod-lambda-admin"
    BUCKET_PREFIX="datadog-log-forwarder-prod"
    ;;
staging)
    AWS_PROFILE_NAME="sso-staging-lambda-admin"
    BUCKET_PREFIX="datadog-log-forwarder-staging"
    ;;
*)
    log_error "The account must be one of staging, prod; got '${ACCOUNT}'"
    ;;
esac

SCRIPT_PATH="$(cd "$(dirname "${0}")" && pwd)/$(basename "${0}")"
cd "$(dirname "${SCRIPT_PATH}")"

if [[ -z ${AWS_VAULT:-} ]]; then
    if ! command -v aws-vault >/dev/null 2>&1; then
        log_error "aws-vault not found"
    fi

    log_info "Acquiring credentials for ${AWS_PROFILE_NAME}..."
    exec aws-vault exec "${AWS_PROFILE_NAME}" -- "${SCRIPT_PATH}" "${@}"
fi


for cmd in aws gh go jq perl unzip yq zip; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        log_error "${cmd} not found, please install it before releasing"
    fi
done

CONFIG_FILE="internal/config/config.go"
TEMPLATE_FILE="template.yaml"
BASE_BRANCH="${BASE_BRANCH:-nabil.dakkoune/go-forwarder}" # TODO: update once merged in main
BUNDLE_PATH="aws-dd-forwarder-${FORWARDER_VERSION}.zip"
VERSIONS_BUCKET="datadog-opensource-asset-versions"
VERSIONS_KEY="forwarder/zip-versions.json"
VERSIONS_JSON_PATH="zip-versions.json"

CURRENT_VERSION=$(perl -ne 'print $1 if /ForwarderVersion\s*=\s*"([^"]+)"/' "${CONFIG_FILE}")

if [[ -z ${CURRENT_VERSION} ]]; then
    log_error "Could not read ForwarderVersion from ${CONFIG_FILE}"
fi

if ! user_confirm "Release ${CURRENT_VERSION} -> ${FORWARDER_VERSION} to ${ACCOUNT}"; then
    log_error "Aborting"
fi

assert_account() {
    local expected current

    expected=$(aws configure get sso_account_id --profile "${AWS_PROFILE_NAME}" 2>/dev/null || true)
    current=$(aws sts get-caller-identity --query "Account" --output text)

    if [[ -n ${expected} && ${current} != "${expected}" ]]; then
        log_error "Credentials are for a different account than ${AWS_PROFILE_NAME} expects; unset AWS_VAULT and re-run"
    fi

    log_info "Authenticated for ${ACCOUNT} as ${AWS_PROFILE_NAME}"
}

assert_bootstrap_zip() {
    local zip_path="${1}"
    local entries

    entries=$(unzip -Z1 "${zip_path}")

    if [[ ${entries} != "bootstrap" ]]; then
        log_error "$(printf "%s must contain exactly one entry named 'bootstrap', found:\n%s" "${zip_path}" "${entries}")"
    fi
}

build_bundle() {
    log_info "Building ${BUNDLE_PATH}..."

    make clean
    make package ZIP_NAME="${BUNDLE_PATH}"
    assert_bootstrap_zip "${BUNDLE_PATH}"

    log_success "Built ${BUNDLE_PATH} ($(wc -c <"${BUNDLE_PATH}" | tr -d '[:space:]') bytes)"
}

publish_bundle() {
    FORWARDER_VERSION="${FORWARDER_VERSION}" \
        BUCKET_PREFIX="${BUCKET_PREFIX}" \
        BUNDLE_PATH="${BUNDLE_PATH}" \
        ./tools/publish_zips.sh
}

# ---------------------------------------------------------------------------
# Signing 
# ---------------------------------------------------------------------------

SIGNING_PROFILE_NAME="DatadogLambdaSigningProfile"
SIGNING_REGION="us-east-1"
SIGNING_BUCKET="dd-lambda-signing-bucket"
SIGNING_UNSIGNED_KEY=""

cleanup_unsigned() {
    if [[ -n ${SIGNING_UNSIGNED_KEY} ]]; then
        aws s3api delete-object --bucket "${SIGNING_BUCKET}" --key "${SIGNING_UNSIGNED_KEY}" \
            --region "${SIGNING_REGION}" >/dev/null 2>&1 || true
        SIGNING_UNSIGNED_KEY=""
    fi
}

sign_bundle() {
    local signed_key job_id status_reason

    SIGNING_UNSIGNED_KEY="$(uuidgen).zip"
    trap cleanup_unsigned EXIT INT TERM

    log_info "Uploading ${BUNDLE_PATH} to s3://${SIGNING_BUCKET}/${SIGNING_UNSIGNED_KEY} for signing..."
    aws s3 cp "${BUNDLE_PATH}" "s3://${SIGNING_BUCKET}/${SIGNING_UNSIGNED_KEY}" --region "${SIGNING_REGION}"

    log_info "Starting the signing job..."
    job_id=$(aws signer start-signing-job \
        --source "s3={bucketName=${SIGNING_BUCKET},key=${SIGNING_UNSIGNED_KEY},version=null}" \
        --destination "s3={bucketName=${SIGNING_BUCKET}}" \
        --profile-name "${SIGNING_PROFILE_NAME}" \
        --region "${SIGNING_REGION}" |
        jq -r '.jobId')

    log_info "Waiting for signing job ${job_id}..."
    if ! aws signer wait successful-signing-job --job-id "${job_id}" --region "${SIGNING_REGION}"; then
        status_reason=$(aws signer describe-signing-job --job-id "${job_id}" \
            --region "${SIGNING_REGION}" | jq -r '.statusReason')
        log_error "Signing job ${job_id} did not succeed: ${status_reason}"
    fi

    signed_key="${job_id}.zip"

    log_info "Replacing the local bundle with the signed one..."
    aws s3 cp "s3://${SIGNING_BUCKET}/${signed_key}" "${BUNDLE_PATH}" --region "${SIGNING_REGION}"

    aws s3api delete-object --bucket "${SIGNING_BUCKET}" --key "${signed_key}" \
        --region "${SIGNING_REGION}" >/dev/null

    cleanup_unsigned
    trap - EXIT INT TERM

    assert_bootstrap_zip "${BUNDLE_PATH}"

    log_success "Successfully signed ${BUNDLE_PATH}"
}

# ---------------------------------------------------------------------------
# Release 
# ---------------------------------------------------------------------------

staging_release() {
    log_info
    log_info "About to release the Go forwarder to STAGING:"
    log_info "\tVersion:  ${FORWARDER_VERSION} (unsigned)"
    log_info "\tAccount:  ${ACCOUNT} (${AWS_PROFILE_NAME})"
    log_info "\tBuckets:  ${BUCKET_PREFIX}-<region>"
    log_info "\tKey:      ${BUNDLE_PATH}"
    log_info
    log_info "No version bump, no signing and no GitHub release happen on this path."
    log_info

    if ! user_confirm "Continue"; then
        log_error "Aborting"
    fi

    build_bundle
    publish_bundle

    log_success "Staging release of ${FORWARDER_VERSION} complete"
    log_info "Point a function at it with:"
    log_info "\t--code S3Bucket=${BUCKET_PREFIX}-<region>,S3Key=${BUNDLE_PATH}"
}

publish_versions_json() {
    jq -n \
        --arg version "${FORWARDER_VERSION}" \
        --arg date "$(date -u +%Y-%m-%d)" \
        '{latest: {forwarder_version: $version, release_date: $date}}' \
        >"${VERSIONS_JSON_PATH}"

    log_info "Uploading ${VERSIONS_KEY} to s3://${VERSIONS_BUCKET}..."
    aws s3 cp "${VERSIONS_JSON_PATH}" "s3://${VERSIONS_BUCKET}/${VERSIONS_KEY}"
    rm -f "${VERSIONS_JSON_PATH}"

    log_success "Published ${FORWARDER_VERSION} as latest"
    log_info "\thttps://${VERSIONS_BUCKET}.s3.amazonaws.com/${VERSIONS_KEY}"
}

prod_asset_push() {
    log_info "Checking out ${BASE_BRANCH}..."
    git checkout "${BASE_BRANCH}"
    git pull origin "${BASE_BRANCH}"

    local git_commit
    git_commit=$(git rev-parse HEAD)

    build_bundle
    sign_bundle
    publish_bundle

    log_info "Creating the draft GitHub pre-release..."
    # TODO: update once forwarder reaches maturity level
    gh release create "aws-dd-forwarder-${FORWARDER_VERSION}" \
        "${BUNDLE_PATH}#aws-dd-forwarder-${FORWARDER_VERSION}.zip" \
        --title "aws-dd-forwarder-${FORWARDER_VERSION}" \
        --target "${git_commit}" \
        --draft \
        --prerelease \
        --latest=false \
        --generate-notes

    publish_versions_json

    log_success "Prod release of ${FORWARDER_VERSION} complete"
    log_info "The release is a non-latest draft pre-release. Add release notes and publish it:"
    log_info "\thttps://github.com/DataDog/datadog-serverless-functions/releases"
}

assert_version_increases() {
    local current_core="${CURRENT_VERSION%%-*}"
    local new_core="${FORWARDER_VERSION%%-*}"
    local current_pre="${CURRENT_VERSION#"${current_core}"}"
    local new_pre="${FORWARDER_VERSION#"${new_core}"}"

    if [[ ${current_core} != "${new_core}" ]]; then
        if [[ $(printf '%s\n%s\n' "${current_core}" "${new_core}" | sort -V | tail -1) == "${new_core}" ]]; then
            return 0
        fi
        log_error "Version ${FORWARDER_VERSION} must be greater than the current ${CURRENT_VERSION}"
    fi

    if [[ -n ${current_pre} && -z ${new_pre} ]]; then
        return 0
    fi

    if [[ -n ${current_pre} && -n ${new_pre} &&
        $(printf '%s\n%s\n' "${CURRENT_VERSION}" "${FORWARDER_VERSION}" | sort -V | tail -1) == "${FORWARDER_VERSION}" &&
        ${CURRENT_VERSION} != "${FORWARDER_VERSION}" ]]; then
        return 0
    fi

    log_error "Version ${FORWARDER_VERSION} must be greater than the current ${CURRENT_VERSION}"
}

prod_release() {
    assert_version_increases

    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)

    if [[ ${current_branch} != "${BASE_BRANCH}" ]]; then
        log_error "Must be on ${BASE_BRANCH} to release, currently on ${current_branch}"
    fi

    if ! git diff --quiet || ! git diff --cached --quiet; then
        log_error "Working tree is dirty, please commit or stash your changes"
    fi

    log_info
    log_info "About to release the Go forwarder to PRODUCTION:"
    log_info "\tVersion:  ${CURRENT_VERSION} -> ${FORWARDER_VERSION} (signed)"
    log_info "\tAccount:  ${ACCOUNT} (${AWS_PROFILE_NAME})"
    log_info "\tBuckets:  ${BUCKET_PREFIX}-<region>"
    log_info "\tKey:      ${BUNDLE_PATH}"
    log_info "\tBranch:   ${BASE_BRANCH}"
    log_info

    if ! user_confirm "Continue"; then
        log_error "Aborting"
    fi

    git pull origin "${BASE_BRANCH}"

    local branch_name="release_${FORWARDER_VERSION}"

    if [[ ! -f ${TEMPLATE_FILE} ]]; then
        log_warning "${TEMPLATE_FILE} not found, its version will not be bumped"
        if ! user_confirm "Continue without bumping the CloudFormation template"; then
            log_error "Aborting"
        fi
    fi

    log_info "Bumping ForwarderVersion to ${FORWARDER_VERSION} in ${CONFIG_FILE}..."
    perl -pi -e "s/(ForwarderVersion\s*=\s*\")[^\"]+/\${1}${FORWARDER_VERSION}/" "${CONFIG_FILE}"

    if git diff --quiet -- "${CONFIG_FILE}"; then
        log_error "Bumping ${CONFIG_FILE} produced no change, please check the file by hand"
    fi

    git checkout -b "${branch_name}"
    git add "${CONFIG_FILE}"

    if [[ -f ${TEMPLATE_FILE} ]]; then
        log_info "Bumping DdForwarder.Version to ${FORWARDER_VERSION} in ${TEMPLATE_FILE}..."
        yq --inplace ".Mappings.Constants.DdForwarder.Version |= \"${FORWARDER_VERSION}\"" "${TEMPLATE_FILE}"
        git add "${TEMPLATE_FILE}"
    fi

    git commit --signoff \
        --message "ci(release): update version from ${CURRENT_VERSION} to ${FORWARDER_VERSION}"
    git push origin "${branch_name}"

    gh pr create \
        --base "${BASE_BRANCH}" \
        --head "${branch_name}" \
        --title "Update version from ${CURRENT_VERSION} to ${FORWARDER_VERSION}" \
        --body "This PR updates the AWS Forwarder version to ${FORWARDER_VERSION}."

    log_info
    if ! user_confirm "Review and merge the pull-request before continuing. Continue"; then
        log_warning "Aborting. Once the pull-request is merged, resume with:"
        log_warning "\tPROD_GITHUB_RESTART=true ${SCRIPT_PATH} ${FORWARDER_VERSION} ${ACCOUNT}"
        exit 1
    fi

    prod_asset_push
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

assert_account

if [[ ${ACCOUNT} == "staging" ]]; then
    staging_release
elif [[ ${PROD_GITHUB_RESTART:-} == "true" ]]; then
    log_info "PROD_GITHUB_RESTART is set, skipping the version bump and going straight to publishing"
    prod_asset_push
else
    prod_release
fi
