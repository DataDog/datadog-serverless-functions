#!/bin/sh

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2020 Datadog, Inc.

# Tests installation and deployment process of forwarder, and that CloudFormation template works.
set -e

# Deploy the stack to a less commonly used region to avoid any problems with limits
AWS_REGION="us-west-2"

# Move into the root directory, so this script can be called from any directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR/..

RUN_ID=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c10)

# Since we never run the log forwarder, api key can be anything.
DD_API_KEY=RUN_ID

CURRENT_VERSION="$(grep -o 'Version: \d\+\.\d\+\.\d\+' template.yaml | cut -d' ' -f2)"

# Make sure we aren't trying to do anything on Datadog's production account. We don't want our
# integration tests to accidentally release a new version of the forwarder
AWS_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
if [ "$AWS_ACCOUNT" = "464622532012" ] ; then
    echo "Detected production credentials. Aborting"
    exit 1
fi

# Run script in this process. This gives us TEMPLATE_URL and FORWARDER_SOURCE_URL env vars
. release.sh $CURRENT_VERSION sandbox

function param {
    KEY=$1
    VALUE=$2
    echo "{\"ParameterKey\":\"${KEY}\",\"ParameterValue\":${VALUE}}"
}

PARAM_LIST=[$(param DdApiKey \"${DD_API_KEY}\"),$(param DdSite \"datadoghq.com\"),$(param SourceZipUrl \"${FORWARDER_SOURCE_URL}\")]
echo "Setting params ${PARAM_LIST}"

# Create an instance of the stack
STACK_NAME="datadog-forwarder-integration-stack-${RUN_ID}"
echo "Creating stack ${STACK_NAME}"
aws cloudformation create-stack --stack-name $STACK_NAME --template-url $TEMPLATE_URL --capabilities "CAPABILITY_AUTO_EXPAND" "CAPABILITY_IAM" --on-failure "DELETE" \
    --parameters=$PARAM_LIST --region $AWS_REGION

echo "Waiting for stack to complete creation ${STACK_NAME}"
aws cloudformation wait stack-create-complete --stack-name $STACK_NAME --region $AWS_REGION

echo "Completed stack creation"

echo "Cleaning up stack"
aws cloudformation delete-stack --stack-name $STACK_NAME  --region $AWS_REGION