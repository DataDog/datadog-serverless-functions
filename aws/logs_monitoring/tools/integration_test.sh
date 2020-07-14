#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc

set -e

# Move into the tools directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR

# Default to Python 3.7
# But switch to Python 3.8 if argument is passed
if [ -z "$1" ]; then
    PYTHON_VERSION="python3.7"
elif [[ $1 = "python3.7" ]]; then
    PYTHON_VERSION="python3.7"
elif [[ $1 = "python3.8" ]]; then
    PYTHON_VERSION="python3.8"
else
    echo "Must use either python3.7 or python3.8"
    exit 1
fi

./build_bundle.sh 0.0.0
cd ../.forwarder
unzip aws-dd-forwarder-0.0.0 -d aws-dd-forwarder-0.0.0
cd $DIR

echo "Building Docker Image"
docker build --file "${DIR}/Dockerfile_integration" -t "datadog-log-forwarder:$PYTHON_VERSION" ../.forwarder --no-cache \
    --build-arg forwarder='aws-dd-forwarder-0.0.0' \
    --build-arg image="lambci/lambda:${PYTHON_VERSION}"

echo "Running integration tests for ${PYTHON_VERSION}"
PYTHON_RUNTIME=${PYTHON_VERSION} docker-compose up --build --abort-on-container-exit
