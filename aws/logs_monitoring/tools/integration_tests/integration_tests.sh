#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc

set -e

# Defaults
PYTHON_VERSION="python3.7"
SKIP_FORWARDER_BUILD=false
UPDATE_SNAPSHOTS=false
LOG_LEVEL=info

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
	esac
done

if [ $PYTHON_VERSION != "python3.7" ] && [ $PYTHON_VERSION != "python3.8" ]; then
    echo "Must use either Python 3.7 or 3.8"
    exit 1
fi

INTEGRATION_TESTS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# Build the Forwarder
if ! [ $SKIP_FORWARDER_BUILD == true ]; then
	cd $INTEGRATION_TESTS_DIR
	cd ../
	./build_bundle.sh 0.0.0
	cd ../.forwarder
	unzip aws-dd-forwarder-0.0.0 -d aws-dd-forwarder-0.0.0
fi

cd $INTEGRATION_TESTS_DIR

# Build Docker image of Forwarder for tests
echo "Building Docker Image for Forwarder"
docker build --file "${INTEGRATION_TESTS_DIR}/forwarder/Dockerfile" -t "datadog-log-forwarder:$PYTHON_VERSION" ../../.forwarder --no-cache \
    --build-arg forwarder='aws-dd-forwarder-0.0.0' \
    --build-arg image="lambci/lambda:${PYTHON_VERSION}"

echo "Running integration tests for ${PYTHON_VERSION}"
LOG_LEVEL=${LOG_LEVEL} UPDATE_SNAPSHOTS=${UPDATE_SNAPSHOTS} PYTHON_RUNTIME=${PYTHON_VERSION} docker-compose up --build --abort-on-container-exit
