#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

# Releases the Datadog Forwarder.
#
# Usage: ./scripts/release.sh [--skip-build] [--skip-sign] [--skip-publish]
#                              [--skip-template] [--skip-versions-json]
#                              [--skip-gh-release] VERSION
#
# Environment:
#   DRY_RUN        defaults to "true"; set to "false" to actually sign/publish/release.
#   OVERWRITE      "true" republishes over already-published S3 keys
#   REGIONS        space-separated override for the commercial regions
#   SKIP_REGIONS   space-separated regions to exclude from the commercial regions
#
#
# The --skip-* flags resume a real (DRY_RUN=false) release that failed
# partway, at a coarse step boundary; scripts/publish_zip.sh's own
# already-published skip logic resumes at a finer per-region boundary within
# a step that already ran. Neither replaces the other.

set -o nounset -o pipefail -o errexit

# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
cd "$(dirname "$0")/.."

DRY_RUN="${DRY_RUN:-true}"

help() {
    cat <<'EOF'
Usage: ./scripts/release.sh [--skip-build] [--skip-sign] [--skip-publish]
                             [--skip-template] [--skip-versions-json]
                             [--skip-gh-release] VERSION

Environment:
  DRY_RUN        defaults to "true"; set to "false" to actually sign/publish/release.
  OVERWRITE      "true" republishes over already-published S3 keys
  REGIONS        space-separated override for the commercial regions
  SKIP_REGIONS   space-separated regions to exclude from the commercial regions

The --skip-* flags resume a real (DRY_RUN=false) release that failed
partway, at a coarse step boundary; scripts/publish_zip.sh's own
already-published skip logic resumes at a finer per-region boundary within
a step that already ran. Neither replaces the other.
EOF
}


# ---------------------------------------------------------------------------
# Branch
# ---------------------------------------------------------------------------
EXPECTED_BRANCH="master"

# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
COMMERCIAL_PROFILE="sso-prod-lambda-admin"
GOV_PROFILE="sso-gov-cloud-us1-fed-engineering"
SIGNING_PROFILE_NAME="DatadogLambdaSigningProfile"

# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------
# We get the all the commercial regions from XXX
FIPS_COMMERCIAL_REGIONS="us-east-1 us-east-2 us-west-1 us-west-2"
GOV_REGIONS="us-gov-west-1"
SKIP_REGIONS="${SKIP_REGIONS:-me-central-1 me-south-1}"

# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------
SIGNING_REGION="us-east-1"
SIGNING_BUCKET="dd-lambda-signing-bucket"

# ---------------------------------------------------------------------------
# Version assets
# ---------------------------------------------------------------------------
VERSIONS_BUCKET="datadog-opensource-asset-versions"
VERSIONS_KEY="forwarder/zip-versions.json"
VERSIONS_JSON_PATH="zip-versions.json"

# ---------------------------------------------------------------------------
# Code bucket prefix
# ---------------------------------------------------------------------------
BUCKET_PREFIX="datadog-log-forwarder-prod"

# ---------------------------------------------------------------------------
# CloudFormation
# ---------------------------------------------------------------------------
CF_KEY="aws/forwarder/v6/latest.yaml"
CF_COMMERCIAL_BUCKET="datadog-cloudformation-template"
CF_GOV_BUCKET="datadog-cloudformation-template-us-gov"

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
ORIGINAL_ARGS=("${@}")
SKIP_BUILD=0 SKIP_SIGN=0 SKIP_PUBLISH=0 SKIP_TEMPLATE=0 SKIP_VERSIONS_JSON=0 SKIP_GH_RELEASE=0
POSITIONAL=()

while test $# -gt 0; do
    case "$1" in
    -h | --help)
        help
        exit 0
        ;;
    --skip-build)
        SKIP_BUILD=1
        shift
        ;;
    --skip-sign)
        SKIP_SIGN=1
        shift
        ;;
    --skip-publish)
        SKIP_PUBLISH=1
        shift
        ;;
    --skip-template)
        SKIP_TEMPLATE=1
        shift
        ;;
    --skip-versions-json)
        SKIP_VERSIONS_JSON=1
        shift
        ;;
    --skip-gh-release)
        SKIP_GH_RELEASE=1
        shift
        ;;
    *)
        POSITIONAL+=("$1")
        shift
        ;;
    esac
done
set -- "${POSITIONAL[@]}"

if [[ $# -ne 1 ]]; then
    help
    log_error "Expected exactly one VERSION argument, got ${#}"
fi

VERSION="$1"
ZIP_PATH="aws-dd-forwarder-${VERSION}.zip"
FIPS_ZIP_PATH="aws-dd-forwarder-${VERSION}-fips.zip"

assert_version_format() {
    if [[ ! ${VERSION} =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]]; then
        log_error "The version must use the format <major>.<minor>.<patch>[-prerelease], got '${VERSION}'"
    fi
}

assert_version_format

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

if [[ "${DRY_RUN}" != "true" && -z ${AWS_VAULT:-} ]]; then
    if ! command -v aws-vault >/dev/null 2>&1; then
        log_error "aws-vault not found"
    fi

    log_info "Acquiring credentials for ${COMMERCIAL_PROFILE}..."
    exec aws-vault exec "${COMMERCIAL_PROFILE}" -- "$0" "${ORIGINAL_ARGS[@]}"
fi

for cmd in aws aws-vault curl gh go jq make perl unzip uuidgen yq zip; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        log_error "${cmd} not found, please install it before releasing"
    fi
done

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

assert_clean_tree() {
    if ! git diff --quiet || ! git diff --cached --quiet; then
        log_error "Working tree is dirty, please commit or stash your changes"
    fi
}

assert_local_branch() {
    local current_branch
    current_branch="$(git rev-parse --abbrev-ref HEAD)"

    if [[ ${current_branch} != "${EXPECTED_BRANCH}" ]]; then
        log_warning "You are releasing from '${current_branch}', not '${EXPECTED_BRANCH}'."
        if ! user_confirm "Are you sure?"; then
            log_error "Aborting"
        fi
    fi
}

assert_remote_branch() {
    local current_branch upstream counts behind ahead

    current_branch="$(git rev-parse --abbrev-ref HEAD)"
    run_traced git fetch origin "${current_branch}"

    upstream="origin/${current_branch}"
    if ! git rev-parse --verify --quiet "${upstream}" >/dev/null; then
        log_warning "No '${upstream}' remote branch found; skipping sync check"
        return 0
    fi

    counts="$(git rev-list --left-right --count "${upstream}...HEAD")"
    behind="$(cut -f1 <<<"${counts}")"
    ahead="$(cut -f2 <<<"${counts}")"

    if [[ ${behind} -gt 0 ]]; then
        log_error "Local '${current_branch}' is ${behind} commit(s) behind '${upstream}'; pull before releasing"
    fi

    if [[ ${ahead} -gt 0 ]]; then
        log_error "Local '${current_branch}' is ${ahead} commit(s) ahead of '${upstream}'; push before releasing, otherwise '--target ${GIT_COMMIT}' won't exist on GitHub"
    fi
}

assert_gh_auth() {
    if [[ ${SKIP_GH_RELEASE} -eq 1 ]]; then
        return 0
    fi

    if ! gh auth status &>/dev/null; then
        log_error "GitHub authentication failed for gh. Please run: gh auth login"
    fi
}

assert_version_increases() {
    local current_core="${CURRENT_VERSION%%-*}"
    local new_core="${VERSION%%-*}"
    local current_pre="${CURRENT_VERSION#"${current_core}"}"
    local new_pre="${VERSION#"${new_core}"}"

    if [[ ${current_core} != "${new_core}" ]]; then
        if [[ $(printf '%s\n%s\n' "${current_core}" "${new_core}" | sort -V | tail -1) == "${new_core}" ]]; then
            return 0
        fi
        log_error "Version ${VERSION} must be greater than the current ${CURRENT_VERSION}"
    fi

    if [[ -n ${current_pre} && -z ${new_pre} ]]; then
        return 0
    fi

    if [[ -n ${current_pre} && -n ${new_pre} &&
        $(printf '%s\n%s\n' "${CURRENT_VERSION}" "${VERSION}" | sort -V | tail -1) == "${VERSION}" &&
        ${CURRENT_VERSION} != "${VERSION}" ]]; then
        return 0
    fi

    log_error "Version ${VERSION} must be greater than the current ${CURRENT_VERSION}"
}

GIT_COMMIT="$(git rev-parse HEAD)"

if [[ "${DRY_RUN}" != "true" ]]; then
    assert_clean_tree
    assert_local_branch
    assert_remote_branch
    assert_gh_auth
fi

CURRENT_VERSION="$(curl -fsSL "https://${VERSIONS_BUCKET}.s3.amazonaws.com/${VERSIONS_KEY}" | jq -r '.latest.forwarder_version // empty')"
if [[ -z ${CURRENT_VERSION} ]]; then
    log_error "Could not read the current forwarder_version from https://${VERSIONS_BUCKET}.s3.amazonaws.com/${VERSIONS_KEY}"
fi

assert_version_increases

if [[ "${DRY_RUN}" != "true" ]]; then
    log_info
    log_info "About to release the Go forwarder to PRODUCTION:"
    log_info "\tVersion:    ${CURRENT_VERSION} -> ${VERSION}"
    log_info "\tCommit:     ${GIT_COMMIT}"
    log_info "\tCommercial: ${ZIP_PATH}, ${FIPS_ZIP_PATH} (regions: ${FIPS_COMMERCIAL_REGIONS})"
    log_info "\tGovCloud:   ${FIPS_ZIP_PATH} (regions: ${GOV_REGIONS})"
    log_info

    if ! user_confirm "Continue"; then
        log_error "Aborting"
    fi
fi

# ---------------------------------------------------------------------------
# Build + verify
# ---------------------------------------------------------------------------

assert_bootstrap_zip() {
    local zip_path="$1"
    local entries

    entries=$(unzip -Z1 "${zip_path}")

    if ! grep -qx 'bootstrap' <<<"${entries}"; then
        log_error "$(printf "%s must contain 'bootstrap', found:\n%s" "${zip_path}" "${entries}")"
    fi
}

assert_version_embedded() {
    local zip_path="$1"
    local tmp_bin embedded_strings

    tmp_bin="$(mktemp)"
    unzip -p "${zip_path}" bootstrap >"${tmp_bin}"
    embedded_strings="$(strings "${tmp_bin}")"
    rm -f "${tmp_bin}"

    if ! grep -qxF "${VERSION}" <<<"${embedded_strings}"; then
        log_error "${zip_path} does not appear to embed version ${VERSION}"
    fi
}

if [[ ${SKIP_BUILD} -eq 0 ]]; then
    log_info "Building ${ZIP_PATH} and ${FIPS_ZIP_PATH}..."
    run_traced make clean
    run_traced make package VERSION="${VERSION}" GOFIPS140=off
    run_traced make package VERSION="${VERSION}" GOFIPS140=latest
else
    log_warning "Skipping build (--skip-build), verifying the zips already on disk"
fi

for zip_path in "${ZIP_PATH}" "${FIPS_ZIP_PATH}"; do
    assert_bootstrap_zip "${zip_path}"
    assert_version_embedded "${zip_path}"
done

log_success "Built and verified ${ZIP_PATH} and ${FIPS_ZIP_PATH}"

# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

SIGNING_UNSIGNED_KEY=""

cleanup_unsigned() {
    if [[ -n ${SIGNING_UNSIGNED_KEY} ]]; then
        aws s3api delete-object --bucket "${SIGNING_BUCKET}" --key "${SIGNING_UNSIGNED_KEY}" \
            --region "${SIGNING_REGION}" >/dev/null 2>&1 || true
        SIGNING_UNSIGNED_KEY=""
    fi
}

sign_bundle() {
    local bundle_path="$1"
    local signed_key job_id status_reason

    SIGNING_UNSIGNED_KEY="$(uuidgen).zip"
    trap cleanup_unsigned EXIT INT TERM

    log_info "Uploading ${bundle_path} to s3://${SIGNING_BUCKET}/${SIGNING_UNSIGNED_KEY} for signing..."
    run_traced aws s3 cp "${bundle_path}" "s3://${SIGNING_BUCKET}/${SIGNING_UNSIGNED_KEY}" --region "${SIGNING_REGION}"

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
    run_traced aws s3 cp "s3://${SIGNING_BUCKET}/${signed_key}" "${bundle_path}" --region "${SIGNING_REGION}"

    aws s3api delete-object --bucket "${SIGNING_BUCKET}" --key "${signed_key}" \
        --region "${SIGNING_REGION}" >/dev/null

    cleanup_unsigned
    trap - EXIT INT TERM

    assert_bootstrap_zip "${bundle_path}"

    log_success "Successfully signed ${bundle_path}"
}

if [[ ${SKIP_SIGN} -eq 1 ]]; then
    log_warning "Skipping signing (--skip-sign)"
elif [[ "${DRY_RUN}" == "true" ]]; then
    log_warning "[dry-run] would sign ${ZIP_PATH} and ${FIPS_ZIP_PATH}"
else
    sign_bundle "${ZIP_PATH}"
    sign_bundle "${FIPS_ZIP_PATH}"
fi

# ---------------------------------------------------------------------------
# Publish zips
# ---------------------------------------------------------------------------

if [[ ${SKIP_PUBLISH} -eq 1 ]]; then
    log_warning "Skipping zip publish (--skip-publish)"
else
    BUCKET_PREFIX="${BUCKET_PREFIX}" BUNDLE_PATH="${ZIP_PATH}" SKIP_REGIONS="${SKIP_REGIONS}" \
        dry_run ./scripts/publish_zip.sh

    BUCKET_PREFIX="${BUCKET_PREFIX}" BUNDLE_PATH="${FIPS_ZIP_PATH}" REGIONS="${FIPS_COMMERCIAL_REGIONS}" \
        dry_run ./scripts/publish_zip.sh

    BUCKET_PREFIX="${BUCKET_PREFIX}" BUNDLE_PATH="${FIPS_ZIP_PATH}" REGIONS="${GOV_REGIONS}" \
        dry_run aws-vault exec "${GOV_PROFILE}" -- ./scripts/publish_zip.sh
fi

# ---------------------------------------------------------------------------
# Publish the CloudFormation template
# ---------------------------------------------------------------------------

if [[ ${SKIP_TEMPLATE} -eq 1 ]]; then
    log_warning "Skipping template publish (--skip-template)"
else
    VERSION="${VERSION}" BUCKET="${CF_COMMERCIAL_BUCKET}" KEY="${CF_KEY}" \
        dry_run ./scripts/publish_template.sh

    VERSION="${VERSION}" BUCKET="${CF_GOV_BUCKET}" KEY="${CF_KEY}" \
        dry_run aws-vault exec "${GOV_PROFILE}" -- ./scripts/publish_template.sh
fi

# ---------------------------------------------------------------------------
# Publish zip-versions.json
# ---------------------------------------------------------------------------

publish_versions_json() {
    jq -n \
        --arg version "${VERSION}" \
        --arg date "$(date -u +%Y-%m-%d)" \
        '{latest: {forwarder_version: $version, release_date: $date}}' \
        >"${VERSIONS_JSON_PATH}"

    run_traced aws s3 cp "${VERSIONS_JSON_PATH}" "s3://${VERSIONS_BUCKET}/${VERSIONS_KEY}"
    rm -f "${VERSIONS_JSON_PATH}"

    log_success "Published ${VERSION} as latest"
    log_info "\thttps://${VERSIONS_BUCKET}.s3.amazonaws.com/${VERSIONS_KEY}"
}

if [[ ${SKIP_VERSIONS_JSON} -eq 1 ]]; then
    log_warning "Skipping zip-versions.json publish (--skip-versions-json)"
elif [[ "${DRY_RUN}" == "true" ]]; then
    log_warning "[dry-run] would publish zip-versions.json with forwarder_version=${VERSION}"
else
    publish_versions_json
fi

# ---------------------------------------------------------------------------
# GitHub release
# ---------------------------------------------------------------------------

GH_RELEASE_TAG="aws-dd-forwarder-${VERSION}"

if [[ ${SKIP_GH_RELEASE} -eq 1 ]]; then
    log_warning "Skipping GitHub release (--skip-gh-release)"
elif [[ "${DRY_RUN}" == "true" ]]; then
    log_warning "[dry-run] would create GitHub release ${GH_RELEASE_TAG}, or upload assets to it if it already exists"
elif gh release view "${GH_RELEASE_TAG}" >/dev/null 2>&1; then
    log_warning "${GH_RELEASE_TAG} already exists; uploading assets to it instead of re-creating it"
    run_traced gh release upload "${GH_RELEASE_TAG}" \
        "${ZIP_PATH}#aws-dd-forwarder-${VERSION}.zip" \
        "${FIPS_ZIP_PATH}#aws-dd-forwarder-${VERSION}-fips.zip" \
        --clobber
else
    run_traced gh release create "${GH_RELEASE_TAG}" \
        "${ZIP_PATH}#aws-dd-forwarder-${VERSION}.zip" \
        "${FIPS_ZIP_PATH}#aws-dd-forwarder-${VERSION}-fips.zip" \
        --title "${GH_RELEASE_TAG}" \
        --target "${GIT_COMMIT}" \
        --draft \
        --prerelease \
        --latest=false \
        --generate-notes
fi

log_info
if [[ "${DRY_RUN}" == "true" ]]; then
    log_success "Dry run of ${VERSION} complete."
else
    log_success "Release of ${VERSION} complete."
    log_info "The GitHub release is a non-latest draft pre-release. Add release notes and publish it:"
    log_info "\thttps://github.com/DataDog/datadog-serverless-functions/releases"
fi

if [[ ${SKIP_BUILD} -eq 0 ]]; then
    rm -f bootstrap "${ZIP_PATH}" "${FIPS_ZIP_PATH}"
fi
