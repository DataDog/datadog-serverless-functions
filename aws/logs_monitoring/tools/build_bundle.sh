#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc

set -e

# Move into the tools directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd $DIR

PYTHON_VERSIONS=("3.8.0")
FORWARDER_PREFIX="aws-dd-forwarder"
FORWARDER_DIR="../.forwarder"

function make_path_absolute {
    echo "$(cd "$(dirname "$1")"; pwd)/$(basename "$1")"
}

function docker_build_zip {
    # Args: [python version] [zip destination]

    destination=$(make_path_absolute $2)

    # Install datadogpy in a docker container to avoid the mess from switching
    # between different python runtimes.
    temp_dir=$(mktemp -d)
    docker build --file "${DIR}/Dockerfile_bundle" -t "datadog-bundle:$1" .. --no-cache \
        --build-arg runtime=$1

    # Run the image by runtime tag, tar its generatd `python` directory to sdout,
    # then extract it to a temp directory.
    docker run datadog-bundle:$1 tar cf - . | tar -xf - -C $temp_dir

    # Zip to destination, and keep directory structure as based in $temp_dir
    (cd $temp_dir && zip -q -r $destination ./)

    rm -rf $temp_dir
    echo "Done creating archive $destination"
}

rm -rf $FORWARDER_DIR
mkdir $FORWARDER_DIR

for python_version in "${PYTHON_VERSIONS[@]}"
do
    echo "Building layer for python${python_version}"
    docker_build_zip ${python_version} ${FORWARDER_DIR}/${FORWARDER_PREFIX}${python_version}.zip
done


echo "Done creating forwarder:"
ls $FORWARDER_DIR | xargs -I _ echo "${FORWARDER_DIR}/_"
