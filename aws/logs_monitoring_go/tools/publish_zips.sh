#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

# Publishes a forwarder bundle to one regional S3 bucket per AWS region.
#
# Credentials are inherited from the parent process; this script contains no
# aws-vault logic, so it works both as a release step and standalone:
#
#   FORWARDER_VERSION=6.0.0 \
#   BUCKET_PREFIX=datadog-log-forwarder-staging \
#   BUNDLE_PATH=aws-dd-forwarder-6.0.0.zip \
#       aws-vault exec sso-staging-lambda-admin -- ./tools/publish_zips.sh
#
# Optional:
#   REGIONS       space-separated override; defaults to every region enabled in the account
#   SKIP_REGIONS  space-separated regions to exclude; not treated as failures
#   OVERWRITE     "true" republishes over an existing key (see the immutability guard below)

set -o nounset -o pipefail -o errexit

# shellcheck source-path=SCRIPTDIR
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"

for required in FORWARDER_VERSION BUCKET_PREFIX BUNDLE_PATH; do
    if [[ -z ${!required:-} ]]; then
        log_error "${required} is required"
    fi
done

if [[ ! -f ${BUNDLE_PATH} ]]; then
    log_error "Bundle not found: ${BUNDLE_PATH}"
fi

if ! command -v aws >/dev/null 2>&1; then
    log_error "aws not found, please install the AWS CLI"
fi

S3_KEY="aws-dd-forwarder-${FORWARDER_VERSION}.zip"

AWS_TIMEOUTS=(--cli-connect-timeout 10 --cli-read-timeout 30)
if ! aws sts get-caller-identity "${AWS_TIMEOUTS[@]}" >/dev/null 2>&1; then
    log_error "Not authenticated. Wrap this call, e.g. aws-vault exec sso-staging-lambda-admin -- ${0}"
fi

if [[ -z ${REGIONS:-} ]]; then
    log_info "Discovering regions enabled in this account..."
    REGIONS=$(aws ec2 describe-regions "${AWS_TIMEOUTS[@]}" \
        --query "Regions[].RegionName" --output text)
fi

read -r -a REGION_LIST <<<"${REGIONS}"

PUBLISHED_REGIONS=()
OVERWRITTEN_REGIONS=()
UNCHANGED_REGIONS=()
SKIPPED_REGIONS=()
UNREACHABLE_REGIONS=()
FAILED_REGIONS=()

if [[ -n ${SKIP_REGIONS:-} ]]; then
    REMAINING_REGIONS=()
    for region in "${REGION_LIST[@]}"; do
        if [[ " ${SKIP_REGIONS} " == *" ${region} "* ]]; then
            SKIPPED_REGIONS+=("${region}")
        else
            REMAINING_REGIONS+=("${region}")
        fi
    done
    REGION_LIST=("${REMAINING_REGIONS[@]}")
fi

if [[ ${#REGION_LIST[@]} -eq 0 ]]; then
    log_error "No regions to publish to"
fi

local_size=$(wc -c <"${BUNDLE_PATH}" | tr -d '[:space:]')

log_info
log_info "Bundle:  ${BUNDLE_PATH} (${local_size} bytes)"
log_info "Key:     ${S3_KEY}"
log_info "Buckets: ${BUCKET_PREFIX}-<region>"
log_info "Regions: ${#REGION_LIST[@]} (${REGION_LIST[*]})"
if [[ ${#SKIPPED_REGIONS[@]} -gt 0 ]]; then
    log_info "Skipped: ${#SKIPPED_REGIONS[@]} (${SKIPPED_REGIONS[*]})"
fi
log_info

if ! user_confirm "Publish to the ${#REGION_LIST[@]} regions above"; then
    log_error "Aborting"
fi

for region in "${REGION_LIST[@]}"; do
    bucket="${BUCKET_PREFIX}-${region}"
    overwriting="false"

    if ! aws s3api head-bucket "${AWS_TIMEOUTS[@]}" \
        --bucket "${bucket}" --region "${region}" >/dev/null 2>&1; then
        log_warning "[${region}] bucket ${bucket} is missing or unreachable"
        UNREACHABLE_REGIONS+=("${region}")
        continue
    fi

    if aws s3api head-object "${AWS_TIMEOUTS[@]}" \
        --bucket "${bucket}" --key "${S3_KEY}" --region "${region}" >/dev/null 2>&1; then
        if [[ ${OVERWRITE:-} != "true" ]]; then
            log_info "[${region}] ${S3_KEY} already published, skipping"
            UNCHANGED_REGIONS+=("${region}")
            continue
        fi
        overwriting="true"
        log_warning "[${region}] ${S3_KEY} already published, overwriting"
    fi

    log_info "[${region}] uploading ${S3_KEY} to ${bucket}..."
    if ! aws s3 cp "${BUNDLE_PATH}" "s3://${bucket}/${S3_KEY}" --region "${region}"; then
        log_warning "[${region}] upload failed"
        FAILED_REGIONS+=("${region}")
        continue
    fi

    if [[ ${overwriting} == "true" ]]; then
        OVERWRITTEN_REGIONS+=("${region}")
    else
        PUBLISHED_REGIONS+=("${region}")
    fi
done

log_info
log_info "Summary for ${S3_KEY}:"

if [[ ${#PUBLISHED_REGIONS[@]} -gt 0 ]]; then
    log_success "\tpublished:    ${#PUBLISHED_REGIONS[@]} (${PUBLISHED_REGIONS[*]})"
fi
if [[ ${#OVERWRITTEN_REGIONS[@]} -gt 0 ]]; then
    log_warning "\toverwritten:  ${#OVERWRITTEN_REGIONS[@]} (${OVERWRITTEN_REGIONS[*]})"
fi
if [[ ${#UNCHANGED_REGIONS[@]} -gt 0 ]]; then
    log_info "\tunchanged:    ${#UNCHANGED_REGIONS[@]} (${UNCHANGED_REGIONS[*]})"
fi
if [[ ${#SKIPPED_REGIONS[@]} -gt 0 ]]; then
    log_info "\tskipped:      ${#SKIPPED_REGIONS[@]} (${SKIPPED_REGIONS[*]})"
fi
if [[ ${#UNREACHABLE_REGIONS[@]} -gt 0 ]]; then
    log_warning "\tunreachable:  ${#UNREACHABLE_REGIONS[@]} (${UNREACHABLE_REGIONS[*]})"
fi
if [[ ${#FAILED_REGIONS[@]} -gt 0 ]]; then
    log_warning "\tfailed:       ${#FAILED_REGIONS[@]} (${FAILED_REGIONS[*]})"
fi

UNPUBLISHED_REGIONS=("${UNREACHABLE_REGIONS[@]}" "${FAILED_REGIONS[@]}")

if [[ ${#UNPUBLISHED_REGIONS[@]} -eq 0 ]]; then
    log_info
    log_success "${S3_KEY} is published in every targeted region"
    exit 0
fi

log_info
log_warning "${#UNPUBLISHED_REGIONS[@]} region(s) did not receive ${S3_KEY}:"
log_warning "\t${UNPUBLISHED_REGIONS[*]}"
log_warning "Retry just those with:"
log_warning "\tREGIONS=\"${UNPUBLISHED_REGIONS[*]}\" ${0}"
log_info

if user_confirm "Continue anyway with a partial publish"; then
    log_warning "Continuing; ${S3_KEY} is missing from ${#UNPUBLISHED_REGIONS[@]} region(s)"
    exit 0
fi

if [[ ${#PUBLISHED_REGIONS[@]} -eq 0 ]]; then
    log_error "Aborted. This run uploaded nothing, so there is nothing to roll back"
fi

log_info
if ! user_confirm "Roll back by deleting ${S3_KEY} from the ${#PUBLISHED_REGIONS[@]} region(s) this run uploaded"; then
    log_error "Aborted without rolling back; ${S3_KEY} is still present in: ${PUBLISHED_REGIONS[*]}"
fi

ROLLBACK_FAILED_REGIONS=()

for region in "${PUBLISHED_REGIONS[@]}"; do
    if aws s3api delete-object "${AWS_TIMEOUTS[@]}" \
        --bucket "${BUCKET_PREFIX}-${region}" --key "${S3_KEY}" \
        --region "${region}" >/dev/null 2>&1; then
        log_info "[${region}] removed ${S3_KEY}"
    else
        log_warning "[${region}] could not remove ${S3_KEY}"
        ROLLBACK_FAILED_REGIONS+=("${region}")
    fi
done

if [[ ${#OVERWRITTEN_REGIONS[@]} -gt 0 ]]; then
    log_warning "Left in place, deleting would not restore what this run replaced:"
    log_warning "\t${OVERWRITTEN_REGIONS[*]}"
fi

if [[ ${#ROLLBACK_FAILED_REGIONS[@]} -gt 0 ]]; then
    log_error "$(printf "Rollback incomplete. %s is STILL PRESENT in: %s\nRemove it by hand before retrying the release." \
        "${S3_KEY}" "${ROLLBACK_FAILED_REGIONS[*]}")"
fi

log_success "Rolled back ${#PUBLISHED_REGIONS[@]} region(s); ${S3_KEY} no longer exists there"
exit 1
