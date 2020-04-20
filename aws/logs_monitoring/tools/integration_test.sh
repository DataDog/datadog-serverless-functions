#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc

set -e

# Move into the tools directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR

PYTHON_VERSIONS=("python3.7")

./build_bundle.sh 0.0.0
cd ../.forwarder
unzip aws-dd-forwarder-0.0.0 -d aws-dd-forwarder-0.0.0
cd $DIR

i=0
for python_version in "${PYTHON_VERSIONS[@]}"
do
    echo "Building Docker Image"
    docker build --file "${DIR}/Dockerfile_integration" -t "datadog-log-forwarder:$python_version" ../.forwarder --no-cache \
        --build-arg forwarder='aws-dd-forwarder-0.0.0' \
        --build-arg image="lambci/lambda:${python_version}"

    echo "Running integration tests for ${python_version}"
    PYTHON_RUNTIME=${python_version} docker-compose up --build --abort-on-container-exit
    i=$(expr $i + 1)
done
