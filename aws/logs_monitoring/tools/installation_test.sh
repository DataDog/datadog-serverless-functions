#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

# Tests installation and deployment process of forwarder, and that CloudFormation template works.
set -e

# Deploy the stack to a less commonly used region to avoid any problems with limits
AWS_REGION="us-west-2"

# Limits any layer publishing to the test region
export REGIONS=$AWS_REGION
# Prevents the scripts from asking permission 
export NO_INPUT=true

# Move into the root directory, so this script can be called from any directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR/..

RUN_ID=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c10)

# Since we never run the log forwarder, api key can be anything.
DD_API_KEY=RUN_ID

CURRENT_VERSION="$(grep -E -o 'Version: [0-9]+\.[0-9]+\.[0-9]+' template.yaml | cut -d' ' -f2)"

function aws-login() {
    cfg=( "$@" )
    shift
    if [ "$ACCOUNT" = "prod" ] ; then
        aws-vault exec prod-engineering --  ${cfg[@]}
    else
        aws-vault exec sandbox-account-admin --  ${cfg[@]}
    fi
}

# Run script in this process. This gives us TEMPLATE_URL, NEXT_LAYER_VERSION and FORWARDER_SOURCE_URL env vars
. release.sh $CURRENT_VERSION sandbox

function param {
    KEY=$1
    VALUE=$2
    echo "{\"ParameterKey\":\"${KEY}\",\"ParameterValue\":${VALUE}}"
}
echo $FORWARDER_SOURCE_URL

publish_test() {
    ADDED_PARAMS=$1

    PARAM_LIST=[$(param DdApiKey \"${DD_API_KEY}\"),$(param DdSite \"datadoghq.com\"),$(param ReservedConcurrency \"1\"),$ADDED_PARAMS]
    echo "Setting params ${PARAM_LIST}"

    # Create an instance of the stack
    STACK_NAME="datadog-forwarder-integration-stack-${RUN_ID}"

    echo "Creating stack using Zip Copier Flow ${STACK_NAME}"
    aws-login aws cloudformation create-stack --stack-name $STACK_NAME --template-url $TEMPLATE_URL --capabilities "CAPABILITY_AUTO_EXPAND" "CAPABILITY_IAM" --on-failure "DELETE" \
        --parameters=$PARAM_LIST --region $AWS_REGION

    echo "Waiting for stack to complete creation ${STACK_NAME}"
    aws-login aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $AWS_REGION

    echo "Completed stack creation"

    echo "Cleaning up stack"
    aws-login aws cloudformation delete-stack --stack-name $STACK_NAME  --region $AWS_REGION
}

echo
echo "Running Publish with Zip Copier test"
publish_test "$(param SourceZipUrl \"${FORWARDER_SOURCE_URL}\"),$(param InstallAsLayer \"false\")"

RUN_ID=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c10)

echo
echo "Running Publish with Layer test"
LAYER_ARN="arn:aws:lambda:${AWS_REGION}:${CURRENT_ACCOUNT}:layer:${LAYER_NAME}:${LAYER_VERSION}"
publish_test $(param LayerARN \"${LAYER_ARN}\")
