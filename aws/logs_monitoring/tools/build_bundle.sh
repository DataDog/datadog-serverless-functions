#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc

set -e

# Move into the tools directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR

# Read the desired version
if [ -z "$1" ]; then
    echo "Must specify a desired version number"
    exit 1
elif [[ ! $1 =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
    echo "Must use a semantic version, e.g., 3.1.4"
    exit 1
else
    VERSION=$1
fi

PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
FORWARDER_PREFIX="aws-dd-forwarder"
FORWARDER_DIR="../.forwarder"

function make_path_absolute {
    echo "$(cd "$(dirname "$1")"; pwd)/$(basename "$1")"
}

../trace_forwarder/scripts/build_linux_go_bin.sh

function docker_build_zip {
    # Args: [python version] [zip destination]
    zip_destination=$(make_path_absolute $2)
    layer_destination=$(make_path_absolute $3)

    # Install datadogpy in a docker container to avoid the mess from switching
    # between different python runtimes.
    temp_dir=$(mktemp -d)

    docker buildx build --platform linux/amd64 --file "${DIR}/Dockerfile_bundle" -t "datadog-bundle:$1" .. --no-cache \
        --build-arg runtime=$PYTHON_VERSION

    # Run the image by runtime tag, tar its generated `python` directory to sdout,
    # then extract it to a temp directory.
    docker run datadog-bundle:$1 tar cf - . | tar -xf - -C $temp_dir

    # Zip to destination, and keep directory structure as based in $temp_dir
    (cd $temp_dir && zip -q -r $zip_destination ./)

    rm -rf $temp_dir
    echo "Done creating forwarder zip archive $zip_destination"

    temp_dir=$(mktemp -d)
    SUB_DIRECTORY=python
    mkdir $temp_dir/$SUB_DIRECTORY

    # Run the image by runtime tag, tar its generated `python` directory to sdout,
    # then extract it to a temp directory.
    docker run datadog-bundle:$1 tar cf - . | tar -xf - -C $temp_dir/$SUB_DIRECTORY

    # Zip to destination, and keep directory structure as based in $temp_dir
    (cd $temp_dir && zip -q -r $layer_destination ./)
    echo "Done creating layer zip archive $layer_destination"
}

rm -rf $FORWARDER_DIR
mkdir $FORWARDER_DIR

docker_build_zip ${PYTHON_VERSION} ${FORWARDER_DIR}/${FORWARDER_PREFIX}-${VERSION}.zip  ${FORWARDER_DIR}/${FORWARDER_PREFIX}-${VERSION}-layer.zip

echo "Successfully created Forwarder bundle!"
ls $FORWARDER_DIR | xargs -I _ echo "${FORWARDER_DIR}/_"
