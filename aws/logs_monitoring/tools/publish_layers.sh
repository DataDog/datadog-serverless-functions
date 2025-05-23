#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc.

# Publish the datadog forwarder layer across regions, using the AWS CLI
# Usage: VERSION=5 REGIONS=us-east-1 LAYERS=Datadog-Python27 publish_layers.sh
# VERSION is required.

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

log_warning() {
    local YELLOW='\033[0;33m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${YELLOW}" "${*}" "${RESET}" 1>&2
}

log_error() {
    local RED='\033[0;31m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${RED}" "${*}" "${RESET}" 1>&2
    exit 1
}

user_read_input() {
    if [[ ${#} -lt 2 ]]; then
        var_red "Usage: var_read_input VAR_PROMPT VAR_NAME"
        return 1
    fi

    local VAR_PROMPT="${1}"
    shift

    local VAR_NAME="${1}"
    shift

    if [[ -n ${BASH_VERSION} ]]; then
        read -r -p "${VAR_PROMPT}" "${@}" "${VAR_NAME}" </dev/tty
    elif [[ -n ${ZSH_VERSION} ]]; then
        read -r "${VAR_NAME}?${VAR_PROMPT}" "${@}" </dev/tty
    else
        var_error "Shell not supported for reading user input"
        return 1
    fi
}

user_confirm() {
    local DEFAULT_PROMPT="[y/N]"
    local DEFAULT_RETURN=1

    if [[ ${2:-} == "true" ]] || [[ ${2:-} == "0" ]]; then
        DEFAULT_RETURN=0
        DEFAULT_PROMPT="[Y/n]"
    fi

    local input
    user_read_input "${1:-Are you sure}? ${DEFAULT_PROMPT} " input

    case "${input}" in
    [yY][eE][sS] | [yY])
        return 0
        ;;

    [nN][oO] | [nN])
        return 1
        ;;

    *)
        return ${DEFAULT_RETURN}
        ;;
    esac
}

# Makes sure any subprocesses will be terminated with this process
trap "pkill -P $$; exit 1;" INT

PYTHON_VERSIONS_FOR_AWS_CLI=("python3.13")
LAYER_PATHS=(".forwarder/aws-dd-forwarder-${FORWARDER_VERSION}-layer.zip")
AVAILABLE_LAYERS=("Datadog-Forwarder")
AVAILABLE_REGIONS=$(aws ec2 describe-regions | jq -r '.[] | .[] | .RegionName')

# Check that the layer files exist
for layer_file in "${LAYER_PATHS[@]}"; do
    if [[ ! -f ${layer_file} ]]; then
        log_error "Could not find $layer_file."
    fi
done

# Determine the target regions
if [[ -z ${REGIONS:-} ]]; then
    log_warning "Region not specified, running for all available regions."
    REGIONS=$AVAILABLE_REGIONS
else
    echo "Region specified: ${REGIONS}"
    if [[ $AVAILABLE_REGIONS != *"$REGIONS"* ]]; then
        log_error "Could not find ${REGIONS} in available regions: ${AVAILABLE_REGIONS}"
    fi
fi

# Determine the target layers
if [[ -z ${LAYERS:-} ]]; then
    log_warning "Layer not specified, running for all layers."
    LAYERS=("${AVAILABLE_LAYERS[@]}")
else
    log_info "Layer specified: ${LAYERS}"
    if [[ ! " ${AVAILABLE_LAYERS[@]} " =~ " ${LAYERS} " ]]; then
        log_error "Could not find ${LAYERS} in available layers: ${AVAILABLE_LAYERS[@]}"
    fi
fi

# Determine the target layer version
if [[ -z ${LAYER_VERSION:-} ]]; then
    log_error "Layer version not specified"
else
    log_info "Layer version specified: $LAYER_VERSION"
fi

if [[ ${NO_INPUT:-} == "true" ]]; then
    log_info "Publishing version $LAYER_VERSION of layers ${LAYERS[*]} to regions ${REGIONS[*]}"
elif ! user_confirm "Ready to publish version $LAYER_VERSION of layers ${LAYERS[*]} to regions ${REGIONS[*]}" "true"; then
    exit
fi

index_of_layer() {
    layer_name=$1
    for i in "${!AVAILABLE_LAYERS[@]}"; do
        if [[ ${AVAILABLE_LAYERS[$i]} == "${layer_name}" ]]; then
            echo "${i}"
        fi
    done
}

publish_layer() {
    region="${1}"
    layer_name="${2}"
    aws_version_key="${3}"
    layer_path="${4}"

    version_nbr=$(aws lambda publish-layer-version --layer-name "${layer_name}" \
        --description "Datadog Forwarder Layer Package" \
        --zip-file "fileb://$layer_path" \
        --region "${region}" \
        --compatible-runtimes "${aws_version_key}" \
        --cli-read-timeout 60 |
        jq -r '.Version')

    if [[ -z ${version_nbr:-} ]]; then
        return 1
    fi

    aws lambda add-layer-version-permission --layer-name "${layer_name}" \
        --version-number "${version_nbr}" \
        --statement-id "release-$version_nbr" \
        --action "lambda:GetLayerVersion" --principal "*" \
        --region "${region}" >/dev/null

    echo "${version_nbr}"
}

for region in $REGIONS; do
    log_info "Starting publishing layer for region $region..."

    # Publish the layers for each version of python
    for layer_name in "${LAYERS[@]}"; do
        latest_version=$(aws lambda list-layer-versions --region "${region}" --layer-name "${layer_name}" --query 'LayerVersions[0].Version || `0`')
        if [[ ${latest_version} -ge ${LAYER_VERSION} ]]; then
            log_warning "Layer $layer_name version $LAYER_VERSION already exists in region $region, skipping..."
            continue
        elif [[ ${latest_version} -lt $((LAYER_VERSION - 1)) ]]; then
            log_warning "The latest version of layer ${layer_name} in region ${region} is ${latest_version}"

            if ! user_confirm "Publish all the missing versions including ${LAYER_VERSION}" "true"; then
                log_error "Exiting"
            fi
        fi

        index=$(index_of_layer "${layer_name}")
        aws_version_key="${PYTHON_VERSIONS_FOR_AWS_CLI[$index]}"
        layer_path="${LAYER_PATHS[$index]}"

        while [[ ${latest_version} -lt ${LAYER_VERSION} ]]; do
            latest_version=$(publish_layer "${region}" "${layer_name}" "${aws_version_key}" "${layer_path}")
            log_success "Published version $latest_version for layer $layer_name in region $region"

            # This shouldn't happen unless someone manually deleted the latest version, say 28
            # and then try to republish it again. The published version is actually be 29, because
            # Lambda layers are immutable and AWS will skip deleted version and use the next number.
            if [[ ${latest_version} -gt ${LAYER_VERSION} ]]; then
                log_error "Published version ${latest_version} is greater than the desired version ${LAYER_VERSION}!"
            fi
        done
    done
done

echo "Done !"
