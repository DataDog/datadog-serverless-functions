#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc

set -e

# Move into the tools directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR

# Create the layers directory
rm -rf layers
mkdir layers

DD_PY_LAYER_VERSION=$(grep "464622532012:layer:Datadog-Python37:" ../template.yaml  | sed 's/^.*://')
TRACE_FORWARDER_LAYER_VERSION=$(grep "464622532012:layer:Datadog-Trace-Forwarder-Python37:" ../template.yaml  | sed 's/^.*://')

# Download layers
PYTHON_VERSIONS=("python3.8")

LAYER_SUFFIXES=("38")

function download_layer {
    LAYER_ARN="arn:aws:lambda:us-east-1:464622532012:layer:${2}"
    VERSION=$3
    echo "Downloading layer ${LAYER_ARN} with version ${VERSION}\n"
    URL=$(aws lambda get-layer-version --layer-name ${LAYER_ARN} --version-number ${VERSION} --query Content.Location --output text)
    # Convert to a gzip file, since that can be added as a docker layer
    tmpdir=`mktemp -d`

    curl $URL -o "${tmpdir}/${2}.zip"
    (cd $tmpdir && unzip "${2}.zip")
    rm "${tmpdir}/${2}.zip"
    outfilename="${2}.tar.gz"
    (cd $tmpdir && tar czf "$outfilename" *)
    mv "$tmpdir/$outfilename" "layers/"
    rm -rf $tmpdir
}

i=0
for python_version in "${PYTHON_VERSIONS[@]}"
do
    echo "Downloading layers for ${python_version}"
    dd_layer_name="Datadog-Python${LAYER_SUFFIXES[$i]}"
    trace_forwarder_name="Datadog-Trace-Forwarder-Python${LAYER_SUFFIXES[$i]}"

    download_layer ${python_version} ${dd_layer_name} ${DD_PY_LAYER_VERSION}
    download_layer ${python_version} ${trace_forwarder_name} ${TRACE_FORWARDER_LAYER_VERSION}

    echo "Building Docker Image"
    echo "${DIR}/layers/${dd_layer_name}.tar.gz"
    docker build --file "${DIR}/Dockerfile" -t "datadog-log-forwarder:$python_version" .. --no-cache \
        --build-arg dd_py_layer_zip="tools/layers/${dd_layer_name}.tar.gz" \
        --build-arg dd_tracer_layer_zip="tools/layers/${trace_forwarder_name}.tar.gz" \
        --build-arg image="lambci/lambda:${python_version}"

    echo "Running integration tests for ${python_version}"
    PYTHON_RUNTIME=${python_version} docker-compose up --build --abort-on-container-exit
    i=$(expr $i + 1)
done
