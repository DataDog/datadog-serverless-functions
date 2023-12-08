#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc.

# Copy layers from us-east-1 to new region
# args: [new-region]

set -e 

OLD_REGION='us-east-1'

PYTHON_VERSIONS_FOR_AWS_CLI=("python3.10")
LAYER_NAMES=("Datadog-Forwarder")
NEW_REGION=$1

publish_layer() {
    region=$1
    layer_name=$2
    aws_version_key=$3
    layer_path=$4

    version_nbr=$(aws lambda publish-layer-version --layer-name $layer_name \
        --description "Datadog Lambda Layer for Python" \
        --zip-file "fileb://$layer_path" \
        --region $region \
        --compatible-runtimes $aws_version_key \
                        | jq -r '.Version')

    aws lambda add-layer-version-permission --layer-name $layer_name \
        --version-number $version_nbr \
        --statement-id "release-$version_nbr" \
        --action lambda:GetLayerVersion --principal "*" \
        --region $region

    echo "Published layer for region $region, version $aws_version_key, layer_name $layer_name, layer_version $version_nbr"
}

get_max_version() {
    layer_name=$1
    region=$2
    last_layer_version=$(aws lambda list-layer-versions --layer-name $layer_name --region $region | jq -r ".LayerVersions | .[0] |  .Version")
    if [ "$last_layer_version" == "null" ]; then
        echo 0
    else
        echo $last_layer_version
    fi
}

if [ -z "$1" ]; then
    echo "Region parameter not specified, exiting"
    exit 1
fi

j=0
for layer_name in "${LAYER_NAMES[@]}"; do
    # get latest version
    last_layer_version=$(get_max_version $layer_name $OLD_REGION)
    starting_version=$(get_max_version $layer_name $NEW_REGION)
    starting_version=$(expr $starting_version + 1)

    # exit if region is already all caught up
    if [ $starting_version -gt $last_layer_version ]; then
        echo "INFO: $NEW_REGION is already up to date for $layer_name"
        continue
    fi

    # run for each version of layer
    for i in $(seq 1 $last_layer_version); do 
        layer_path=$layer_name"_"$i.zip
        aws_version_key="${PYTHON_VERSIONS_FOR_AWS_CLI[$j]}"

        # download layer versions 
        URL=$(AWS_REGION=$OLD_REGION aws lambda get-layer-version --layer-name $layer_name --version-number $i --query Content.Location --output text)
        curl $URL -o $layer_path

        # publish layer to new region
        publish_layer $NEW_REGION $layer_name $aws_version_key $layer_path
        rm $layer_path
    done

    j=$(expr $j + 1)
done
