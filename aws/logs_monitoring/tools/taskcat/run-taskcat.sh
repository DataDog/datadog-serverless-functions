#!/bin/bash

set -ex 

if [ -z "$AWS_SSO_PROFILE_NAME" ]; then
    echo "Missing AWS_SSO_PROFILE_NAME - Must specify an AWS profile name"
    exit 1
fi

# aws sso login --profile ${AWS_SSO_PROFILE_NAME}

TASKCAT_S3_BUCKET="lambdaforwarder-taskcat-test"
TASKCAT_PROJECT="aws-lambda-forwarder-taskcat-tests"
#
#if [ -z "$DD_API_KEY" ]; then
#    echo "Missing DD_API_KEY - Must specify a Datadog API key"
#    exit 1
#fi
#
#if [ -z "$DD_APP_KEY" ]; then
#    echo "Missing DD_APP_KEY - Must specify a Datadog APP key"
#    exit 1
#fi
#
mkdir -p ./tmp

for f in ../../template.yaml; do
   sed "s|<BUCKET_PLACEHOLDER>.s3.amazonaws.com/aws/<VERSION_PLACEHOLDER>|${TASKCAT_S3_BUCKET}.s3.amazonaws.com/${TASKCAT_PROJECT}|g" $f > ./tmp/$(basename $f)
done

sed "s|<REPLACE_DD_API_KEY>|${DD_API_KEY}|g ; s|<REPLACE_DD_APP_KEY>|${DD_APP_KEY}|g ; s|<REPLACE_AWS_PROFILE>|${AWS_SSO_PROFILE_NAME}|g" ./.taskcat.yml > ./tmp/.taskcat.yml

taskcat upload -b ${TASKCAT_S3_BUCKET} -k ${TASKCAT_PROJECT} -p tmp

taskcat test run --skip-upload --project-root tmp --no-delete

echo "To delete test stacks, run:"
echo " taskcat test clean ${TASKCAT_PROJECT} -a ${AWS_SSO_PROFILE_NAME}"
