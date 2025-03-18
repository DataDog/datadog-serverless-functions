#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc

set -e

PYTHON_VERSION="python3.12"
PYTHON_VERSION_TAG="3.12"
PYTHON_IMAGE="python:3.12"
SKIP_FORWARDER_BUILD=false
UPDATE_SNAPSHOTS=false
LOG_LEVEL=info
LOGS_WAIT_SECONDS=10
INTEGRATION_TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
SNAPSHOTS_DIR_NAME="snapshots"
SNAPSHOT_DIR="${INTEGRATION_TESTS_DIR}/${SNAPSHOTS_DIR_NAME}/*"
SNAPS=($SNAPSHOT_DIR)
ADDITIONAL_LAMBDA=false
CACHE_TEST=false
DD_FETCH_LAMBDA_TAGS="true"
DD_FETCH_STEP_FUNCTIONS_TAGS="true"

script_start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "Starting script time: $script_start_time"

# Parse arguments
for arg in "$@"; do
        case $arg in
        # -s or --skip-forwarder-build
        # Do not build a new forwarder bundle
        # This saves time running the tests, but any changes to the forwarder will not be reflected
        -s | --skip-forwarder-build)
                SKIP_FORWARDER_BUILD=true
                shift
                ;;
                

        # -u or --update
        # Update the snapshots to reflect this test run
        -u | --update)
                UPDATE_SNAPSHOTS=true
                shift
                ;;

        # -d or --debug
        # Print debug logs
        -d | --debug)
                LOG_LEVEL=debug
                shift
                ;;

        # -a or --additional-lambda
        # Run additionalLambda tests

        # Requires AWS credentials
        # Use aws-vault exec sso-sandbox-account-admin -- ./integration_tests.sh
        -a | --additional-lambda)
                ADDITIONAL_LAMBDA=true
                shift
                ;;

        # -c or --cache-test
        # Run cache test
        -c | --cache-test)
                CACHE_TEST=true
                shift
                ;;
        esac
done

# Build the Forwarder
if ! [ $SKIP_FORWARDER_BUILD == true ]; then
        cd $INTEGRATION_TESTS_DIR
        cd ../
        PYTHON_VERSION=${PYTHON_VERSION#python} ./build_bundle.sh 0.0.0
        cd ../.forwarder
        unzip aws-dd-forwarder-0.0.0 -d aws-dd-forwarder-0.0.0
fi

if [ $CACHE_TEST == true ]; then

        SNAPSHOTS_DIR_NAME="snapshots-cache-test"
        DD_FETCH_LAMBDA_TAGS="true"

        # Deploy test lambda function with tags
        AWS_LAMBDA_FUNCTION_INVOKED="cache_test_lambda"
        TEST_LAMBDA_DIR="$INTEGRATION_TESTS_DIR/$AWS_LAMBDA_FUNCTION_INVOKED"

        cd $TEST_LAMBDA_DIR
        sls deploy

        FORWARDER_ARN="$(aws sts get-caller-identity | jq '.Arn')"
        AWS_ACCOUNT_ID="$(aws sts get-caller-identity | jq '.Account')"

        # Deploy test bucket
        DD_S3_BUCKET_NAME=tags-cache-test
        cat >policy.json <<EOF
{
"Statement": [
  {
    "Effect": "Allow",
    "Principal": {
      "AWS": FORWARDER_ARN
    },
    "Action": [
      "s3:DeleteObject",
      "s3:PutObject",
      "s3:GetObject"
    ],
    "Resource": "arn:aws:s3:::DD_S3_BUCKET_NAME/*"
  }
]
}
EOF
        sed -i '' "s/DD_S3_BUCKET_NAME/${DD_S3_BUCKET_NAME}/g" policy.json
        sed -i '' "s|FORWARDER_ARN|${FORWARDER_ARN}|g" policy.json
        aws s3api create-bucket --bucket $DD_S3_BUCKET_NAME
        aws s3api put-bucket-policy --bucket $DD_S3_BUCKET_NAME --policy file://policy.json
fi

# Deploy additional target Lambdas
if [ $ADDITIONAL_LAMBDA == true ]; then
        SERVERLESS_NAME="forwarder-tests-external-lambda-dev"
        EXTERNAL_LAMBDA_NAMES=("ironmaiden" "megadeth")
        EXTERNAL_LAMBDA1="${SERVERLESS_NAME}-${EXTERNAL_LAMBDA_NAMES[0]}"
        EXTERNAL_LAMBDA2="${SERVERLESS_NAME}-${EXTERNAL_LAMBDA_NAMES[1]}"
        EXTERNAL_LAMBDAS="${EXTERNAL_LAMBDA1},${EXTERNAL_LAMBDA2}"
        EXTERNAL_LAMBDA_DIR="${INTEGRATION_TESTS_DIR}/external_lambda"

        cd $EXTERNAL_LAMBDA_DIR
        sls deploy
fi

cd $INTEGRATION_TESTS_DIR

# Build Docker image of Forwarder for tests
echo "Building Docker Image for Forwarder with tag datadog-log-forwarder:$PYTHON_VERSION"
docker buildx build --platform linux/arm64 --file "${INTEGRATION_TESTS_DIR}/forwarder/Dockerfile" -t "datadog-log-forwarder:$PYTHON_VERSION" ../../.forwarder --no-cache \
        --build-arg forwarder='aws-dd-forwarder-0.0.0' \
        --build-arg image="public.ecr.aws/lambda/python:${PYTHON_VERSION_TAG}-arm64"

echo "Running integration tests for ${PYTHON_VERSION}"
LOG_LEVEL=${LOG_LEVEL} \
        UPDATE_SNAPSHOTS=${UPDATE_SNAPSHOTS} \
        PYTHON_RUNTIME=${PYTHON_VERSION} \
        PYTHON_BASE=${PYTHON_IMAGE} \
        EXTERNAL_LAMBDAS=${EXTERNAL_LAMBDAS} \
        DD_S3_BUCKET_NAME=${DD_S3_BUCKET_NAME} \
        AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID} \
        SNAPSHOTS_DIR_NAME="./${SNAPSHOTS_DIR_NAME}" \
        DD_FETCH_LAMBDA_TAGS=${DD_FETCH_LAMBDA_TAGS} \
        DD_FETCH_STEP_FUNCTIONS_TAGS=${DD_FETCH_STEP_FUNCTIONS_TAGS} \
        docker compose up --build --abort-on-container-exit

if [ $ADDITIONAL_LAMBDA == true ]; then
        echo "Waiting for external lambda logs..."
        sleep $LOGS_WAIT_SECONDS
        cd $EXTERNAL_LAMBDA_DIR

        for EXTERNAL_LAMBDA_NAME in "${EXTERNAL_LAMBDA_NAMES[@]}"; do
                raw_logs=$(sls logs -f $EXTERNAL_LAMBDA_NAME --startTime $script_start_time)

                # Extract json lines first, then the base64 gziped payload
                logs=$(echo -e "$raw_logs" | grep -o '{.*}' | jq -r '.awslogs.data')
                lambda_events=()

                # We break up lines into an array
                IFS=$'\n'
                while IFS= read -r line; do
                        # we filter the first `{}` event in the recorder set up
                        if [ "$line" != "null" ]; then
                                lambda_events+=($(echo -e "$line"))
                        fi
                done <<<"$logs"

                if [ "${#lambda_events[@]}" -eq 0 ]; then
                        echo "FAILURE: No matching logs for the external lambda in Cloudwatch"
                        echo "Check with \`sls logs -f $EXTERNAL_LAMBDA_NAME --startTime $script_start_time\`"
                        exit 1
                fi

                mismatch_found=false
                # Verify every event passed to the AdditionalTargetLambda
                for event in "${lambda_events[@]}"; do
                        event_found=false
                        processed_event=$(echo "$event" | base64 -d | gunzip)

                        for snap_path in "${SNAPS[@]}"; do
                                set +e # Don't exit this script if there is a diff
                                diff_output=$(echo "$processed_event" | diff - $snap_path)
                                if [ $? -eq 0 ]; then
                                        event_found=true
                                fi
                                set -e
                        done

                        if [ "$event_found" = false ]; then
                                mismatch_found=true
                                echo "FAILURE: The following event was not found in the snapshots"
                                echo ""
                                echo "$processed_event"
                                echo ""
                        fi
                done

                if [ "$mismatch_found" = true ]; then
                        sls remove
                        echo "FAILURE: A mismatch between new data and a snapshot was found and printed above."
                        exit 1
                fi
        done

        sls remove
        echo "SUCCESS: No difference found between input events and events in the additional target lambda"
fi

if [ $CACHE_TEST == true ]; then
        echo "Cleanning up cache resources"
        cd $TEST_LAMBDA_DIR
        sls remove

        aws s3api delete-object --bucket $DD_S3_BUCKET_NAME --key "cache.json"
        aws s3api delete-bucket --bucket $DD_S3_BUCKET_NAME

        rm policy.json
fi
