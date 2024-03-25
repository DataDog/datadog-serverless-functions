#!/bin/bash
set -e
# Read the new version
if [ -z "$1" ]; then
    echo "Must specify a desired version number"
    exit 1
else
    LAYER_VERSION=$1
fi

# Read the new version
if [ -z "$2" ]; then
    echo "Must specify a forwarder version"
    exit 1
else
    FORWARDER_VERSION=$2
fi

echo "FORWARDER_VERSION=$FORWARDER_VERSION"

LAYER_VERSION=$LAYER_VERSION FORWARDER_VERSION=$FORWARDER_VERSION aws-vault exec sso-sandbox-account-admin -- ./tools/publish_layers.sh
