#!/bin/sh

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2020 Datadog, Inc.

# Builds Datadogpy layers for lambda functions, using Docker
set -e

# Change to the parent of the directory this script is in
cd $(dirname "$0")/..

docker build -t datadog-go-layer . --build-arg runtime=python:3.7
docker run --rm datadog-go-layer go test -v ./...
