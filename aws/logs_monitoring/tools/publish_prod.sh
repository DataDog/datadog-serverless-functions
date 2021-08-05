#!/bin/bash

# Use with `./publish_prod.sh <DESIRED_NEW_VERSION>

set -e
unset AWS_VAULT

# Ensure on main, and pull the latest
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ $BRANCH != "master" ]; then
    echo "Not on master, aborting"
    exit 1
else
    echo "Updating master"
    git pull origin master
fi

# Ensure no uncommitted changes
if [ -n "$(git status --porcelain)" ]; then
    echo "Detected uncommitted changes, aborting"
    exit 1
fi

# Read the new version
if [ -z "$1" ]; then
    echo "Must specify a layer version"
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

# Ensure AWS access before proceeding
saml2aws login -a govcloud-us1-fed-human-engineering
AWS_PROFILE=govcloud-us1-fed-human-engineering aws sts get-caller-identity
aws-vault exec prod-engineering -- aws sts get-caller-identity

echo
echo "Publishing layers to commercial AWS regions"
LAYER_VERSION=$LAYER_VERSION FORWARDER_VERSION=$FORWARDER_VERSION aws-vault exec prod-engineering -- ./tools/publish_layers.sh

echo "Publishing layers to GovCloud AWS regions"
saml2aws login -a govcloud-us1-fed-human-engineering
LAYER_VERSION=$LAYER_VERSION FORWARDER_VERSION=$FORWARDER_VERSION AWS_PROFILE=govcloud-us1-fed-human-engineering ./tools/publish_layers.sh