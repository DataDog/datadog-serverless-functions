#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

# Builds Datadogpy layers for lambda functions, using Docker
set -e

# Change to the parent of the directory this script is in
cd $(dirname "$0")/..

rm -rf ./bin

# Install datadogpy in a docker container to avoid the mess from switching
# between different python runtimes.

if [[ $(docker image ls | grep -c golang) -lt 1 ]]; then
    docker buildx build --platform linux/arm64 -t golang . --no-cache --build-arg "runtime=python:3.13"
fi

id=$(docker create --platform linux/arm64 golang)
docker cp "${id}:/go/src/github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring/trace_forwarder/bin" .
docker rm -v "${id}"
echo "Done creating archive bin"
