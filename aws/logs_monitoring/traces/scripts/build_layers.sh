#!/bin/sh

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc.

# Builds Datadogpy layers for lambda functions, using Docker
set -e

LAYER_DIR=".layers"
LAYER_FILES_PREFIX="datadog_lambda_py"
PYTHON_VERSIONS=("2.7" "3.6" "3.7" "3.8")

function make_path_absolute {
    echo "$(cd "$(dirname "$1")"; pwd)/$(basename "$1")"
}

rm -rf $LAYER_DIR
mkdir $LAYER_DIR

./scripts/build_linux_go_bin.sh

destination=$(make_path_absolute $LAYER_DIR)

for python_version in "${PYTHON_VERSIONS[@]}"
do
    echo "Building layer for python${python_version}"
    temp_dir=$(mktemp -d)

    runtime=python$python_version
    mkdir -p $temp_dir/python/lib/$runtime/site-packages
    cp -rf trace_forwarder $temp_dir/python/lib/$runtime/site-packages/trace_forwarder
    cp -rf bin $temp_dir/python/lib/$runtime/site-packages/trace_forwarder/bin
    cd $temp_dir
    zip -q -r $destination/${LAYER_FILES_PREFIX}${python_version}.zip .
    cd -
    rm -rf $temp_dir
done


echo "Done creating layers:"
ls $LAYER_DIR | xargs -I _ echo "$LAYER_DIR/_"
