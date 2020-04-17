#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc.

# Publish the datadog python lambda layer across regions, using the AWS CLI
# Usage: publish_layer.sh [region]
# Specifying the region arg will publish the layer for the single specified region

PYTHON_VERSIONS_FOR_AWS_CLI=("python2.7" "python3.6" "python3.7" "python3.8")
LAYER_PATHS=(".layers/datadog_lambda_py2.7.zip" ".layers/datadog_lambda_py3.6.zip" ".layers/datadog_lambda_py3.7.zip" ".layers/datadog_lambda_py3.8.zip")
LAYER_NAMES=("Datadog-Trace-Forwarder-Python27" "Datadog-Trace-Forwarder-Python36" "Datadog-Trace-Forwarder-Python37" "Datadog-Trace-Forwarder-Python38")
AVAILABLE_REGIONS=(us-east-2 us-east-1 us-west-1 us-west-2 ap-east-1 ap-south-1 ap-northeast-2 ap-southeast-1 ap-southeast-2 ap-northeast-1 ca-central-1 eu-north-1 eu-central-1 eu-west-1 eu-west-2 eu-west-3 sa-east-1)

# Check that the layer files exist
for layer_file in "${LAYER_PATHS[@]}"
do
    if [ ! -f $layer_file  ]; then
        echo "Could not find $layer_file."
        exit 1
    fi
done

# Check region arg
if [ -z "$1" ]; then
    echo "Region parameter not specified, running for all available regions."
    REGIONS=("${AVAILABLE_REGIONS[@]}")
else
    echo "Region parameter specified: $1"
    if [[ ! " ${AVAILABLE_REGIONS[@]} " =~ " ${1} " ]]; then
        echo "Could not find $1 in available regions: ${AVAILABLE_REGIONS[@]}"
        echo ""
        echo "EXITING SCRIPT."
        exit 1
    fi
    REGIONS=($1)
fi

echo "Starting publishing layers for regions: ${REGIONS[*]}"

for region in "${REGIONS[@]}"
do
    echo "Starting publishing layer for region $region..."

    # Publish the layers for each version of python
    i=0
    for layer_name in "${LAYER_NAMES[@]}"; do
        aws_version_key="${PYTHON_VERSIONS_FOR_AWS_CLI[$i]}"
        layer_path="${LAYER_PATHS[$i]}"

        version_nbr=$(aws lambda publish-layer-version --layer-name $layer_name \
            --description "Datadog Trace Forwader Lambda Layer" \
            --zip-file "fileb://$layer_path" \
            --region $region \
            --compatible-runtimes $aws_version_key \
                          | jq -r '.Version')

        aws lambda add-layer-version-permission --layer-name $layer_name \
            --version-number $version_nbr \
            --statement-id "release-$version_nbr" \
            --action lambda:GetLayerVersion --principal "*" \
            --region $region

        echo "Published layer for region $region, python version $aws_version_key, layer_name $layer_name, layer_version $version_nbr"

        i=$(expr $i + 1)

    done

done

echo "Done !"
