#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc

set -e

# Defaults
PYTHON_VERSION="python3.7"
SKIP_FORWARDER_BUILD=0

# Parse arguments
for arg in "$@"
do
	case $arg in
		# -s or --skip-forwarder-build
		# Do not build a new forwarder bundle
		# This saves time running the tests, but any changes to the forwarder will not be reflected
		-s|--skip-forwarder-build)
		SKIP_FORWARDER_BUILD=1
		shift
		;;

		# -v or --python-version
		# The version of the Python Lambda runtime to use
		# Must be 3.7 or 3.8
		-v=*|--python-version=*)
		PYTHON_VERSION="python${arg#*=}"
		shift
		;;
	esac
done

if [ $PYTHON_VERSION != "python3.7" ] && [ $PYTHON_VERSION != "python3.8" ]; then
    echo "Must use either Python 3.7 or 3.8"
    exit 1
fi

# Move into the tools directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR

# Build the Forwarder
if ! [ $SKIP_FORWARDER_BUILD == 1 ]; then
	./build_bundle.sh 0.0.0
	cd ../.forwarder
	unzip aws-dd-forwarder-0.0.0 -d aws-dd-forwarder-0.0.0
	cd $DIR
fi

# Build Docker Image for Tests
echo "Building Docker Image"
docker build --file "${DIR}/Dockerfile_integration" -t "datadog-log-forwarder:$PYTHON_VERSION" ../.forwarder --no-cache \
    --build-arg forwarder='aws-dd-forwarder-0.0.0' \
    --build-arg image="lambci/lambda:${PYTHON_VERSION}"

echo "Running integration tests for ${PYTHON_VERSION}"
PYTHON_RUNTIME=${PYTHON_VERSION} docker-compose up --build --abort-on-container-exit
