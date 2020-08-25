#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc

# Usage - run commands from the REPO_ROOT/aws/logs_monitoring directory:
# aws-vault exec sandbox-account-admin -- ./scripts/run_integration_tests

set -e

PYTHON_VERSION="python3.7"
SKIP_FORWARDER_BUILD=false
UPDATE_SNAPSHOTS=false
LOG_LEVEL=info
LOGS_WAIT_SECONDS=10
INTEGRATION_TESTS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
SNAPSHOT_DIR="${INTEGRATION_TESTS_DIR}/snapshots/*"
SNAPS=($SNAPSHOT_DIR)
ADDITIONAL_LAMBDA=false

script_start_time=$(date --iso-8601=seconds)
echo "Starting script time: $script_start_time"

# Parse arguments
for arg in "$@"
do
	case $arg in
		# -s or --skip-forwarder-build
		# Do not build a new forwarder bundle
		# This saves time running the tests, but any changes to the forwarder will not be reflected
		-s|--skip-forwarder-build)
		SKIP_FORWARDER_BUILD=true
		shift
		;;

		# -v or --python-version
		# The version of the Python Lambda runtime to use
		# Must be 3.7 or 3.8
		-v=*|--python-version=*)
		PYTHON_VERSION="python${arg#*=}"
		shift
		;;

		# -u or --update
		# Update the snapshots to reflect this test run
		-u|--update)
		UPDATE_SNAPSHOTS=true
		shift
		;;

		# -d or --debug
		# Print debug logs
		-d|--debug)
		LOG_LEVEL=debug
		shift
		;;

		# -a or --additional-lambda
		# Run additionalLambda tests
		-a|--additional-lambda)
		ADDITIONAL_LAMBDA=true
		shift
		;;
	esac
done

if [ $PYTHON_VERSION != "python3.7" ] && [ $PYTHON_VERSION != "python3.8" ]; then
    echo "Must use either Python 3.7 or 3.8"
    exit 1
fi

# Build the Forwarder
if ! [ $SKIP_FORWARDER_BUILD == true ]; then
	cd $INTEGRATION_TESTS_DIR
	cd ../
	./build_bundle.sh 0.0.0
	cd ../.forwarder
	unzip aws-dd-forwarder-0.0.0 -d aws-dd-forwarder-0.0.0
fi


# Deploy additional target lambda
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
echo "Building Docker Image for Forwarder"
docker build --file "${INTEGRATION_TESTS_DIR}/forwarder/Dockerfile" -t "datadog-log-forwarder:$PYTHON_VERSION" ../../.forwarder --no-cache \
    --build-arg forwarder='aws-dd-forwarder-0.0.0' \
    --build-arg image="lambci/lambda:${PYTHON_VERSION}"

echo "Running integration tests for ${PYTHON_VERSION}"
LOG_LEVEL=${LOG_LEVEL} \
UPDATE_SNAPSHOTS=${UPDATE_SNAPSHOTS} \
PYTHON_RUNTIME=${PYTHON_VERSION} \
EXTERNAL_LAMBDAS=${EXTERNAL_LAMBDAS} \
docker-compose up --build --abort-on-container-exit

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
		done <<< "$logs"

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
		    echo "FAILURE: A mismatch between new data and a snapshot was found and printed above."
		    exit 1
		fi
	done
fi

echo "SUCCESS: No difference found between input events and events in the additional target lambda"