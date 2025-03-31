#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.

# Builds Datadogpy layers for lambda functions, using Docker
set -e

# Change to the parent of the directory this script is in
cd $(dirname "$0")/..

docker buildx build --platform linux/arm64 -t datadog-go-layer . --build-arg runtime=python:3.13
docker run --rm datadog-go-layer go test -v ./...
