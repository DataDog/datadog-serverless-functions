#!/bin/bash

# Usage: ./release.sh <Desired Version> <Account [sandbox|prod]>

set -e

LAYER_NAME="Datadog-Forwarder"

# Read the current version
CURRENT_VERSION=$(grep -E -o 'Version: [0-9]+\.[0-9]+\.[0-9]+' template.yaml | cut -d' ' -f2)

# Read the desired version
if [ -z "$1" ]; then
    echo "ERROR: You must specify a desired version number"
    exit 1
elif [[ ! $1 =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
    echo "ERROR: You must use a semantic version (e.g. 3.1.4)"
    exit 1
else
    FORWARDER_VERSION=$1
fi

BUNDLE_PATH=".forwarder/aws-dd-forwarder-${FORWARDER_VERSION}.zip"

# Check account parameter
VALID_ACCOUNTS=("sandbox" "prod")
if [ -z "$2" ]; then
    echo "ERROR: You must pass an account parameter. Please choose sandbox or prod."
    exit 1
fi
if [[ ! "${VALID_ACCOUNTS[@]}" =~ $2 ]]; then
    echo "ERROR: The account parameter was invalid. Please choose sandbox or prod."
    exit 1
fi

ACCOUNT="${2}"
if [ "$ACCOUNT" = "sandbox" ]; then
    if [ "$DEPLOY_TO_SERVERLESS_SANDBOX" = "true" ] ; then
        BUCKET="datadog-cloudformation-template-serverless-sandbox"
    else
        BUCKET="datadog-cloudformation-template-sandbox"
    fi
fi
if [ "$ACCOUNT" = "prod" ]; then
    BUCKET="datadog-cloudformation-template"
fi

function aws-login() {
    cfg=( "$@" )
    shift
    if [ "$ACCOUNT" = "prod" ] ; then
        aws-vault exec sso-prod-engineering --  ${cfg[@]}
    else
        if [ "$DEPLOY_TO_SERVERLESS_SANDBOX" = "true" ] ; then
            aws-vault exec sso-serverless-sandbox-account-admin --  ${cfg[@]}
        else
            aws-vault exec sso-sandbox-account-admin --  ${cfg[@]}
        fi
    fi
}

get_max_layer_version() {
    last_layer_version=$(aws-login aws lambda list-layer-versions --layer-name $LAYER_NAME --region us-west-2 | jq -r ".LayerVersions | .[0] |  .Version")
    if [ "$last_layer_version" == "null" ]; then
        echo 0
    else
        echo $last_layer_version
    fi
}

# Validate identity
aws-login aws sts get-caller-identity

CURRENT_ACCOUNT="$(aws-login aws sts get-caller-identity --query Account --output text)"
CURRENT_LAYER_VERSION=$(get_max_layer_version)
LAYER_VERSION=$(($CURRENT_LAYER_VERSION +1))

echo
echo "Current layer version is $CURRENT_LAYER_VERSION, next layer version is $LAYER_VERSION"

# Validate the template
echo
echo "Validating template.yaml..."
aws-login aws cloudformation validate-template --template-body file://template.yaml


if [ "$ACCOUNT" = "prod" ] ; then

    if [[ ! $(./tools/semver.sh "$FORWARDER_VERSION" "$CURRENT_VERSION") > 0 ]]; then
        echo "Must use a version greater than the current ($CURRENT_VERSION)"
        exit 1
    fi

    # Make sure we are on the master branch
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ $BRANCH != "master" ]; then
        echo "ERROR: Not on the master branch, aborting."
        exit 1
    fi

    # Confirm to proceed
    echo
    read -p "About to bump the version from ${CURRENT_VERSION} to ${FORWARDER_VERSION}, create a release of aws-dd-forwarder-${FORWARDER_VERSION} on GitHub, upload the template.yaml to s3://${BUCKET}/aws/forwarder/${FORWARDER_VERSION}.yaml and create lambda layer version ${LAYER_VERSION}. Continue (y/n)?" CONT
    if [ "$CONT" != "y" ]; then
        echo "Exiting..."
        exit 1
    fi

    # Get the latest code
    git pull origin master

    # Bump version number in settings.py and template.yml
    echo "Bumping the version number to ${FORWARDER_VERSION}..."
    perl -pi -e "s/DD_FORWARDER_VERSION = \"[0-9\.]+/DD_FORWARDER_VERSION = \"${FORWARDER_VERSION}/g" settings.py
    perl -pi -e "s/Version: [0-9\.]+/Version: ${FORWARDER_VERSION}/g" template.yaml
    perl -pi -e "s/LayerVersion: [0-9\.]+/LayerVersion: ${LAYER_VERSION}/g" template.yaml

    # Commit version number changes to git
    echo "Committing version number change..."
    git add settings.py template.yaml
    git commit -m "Bump version from ${CURRENT_VERSION} to ${FORWARDER_VERSION}"
    git push origin master

    # Build the bundle
    echo
    echo "Building the Forwarder bundle..."
    ./tools/build_bundle.sh "${FORWARDER_VERSION}"

    # Sign the bundle
    echo
    echo "Signing the Forwarder bundle..."
    aws-login ./tools/sign_bundle.sh $BUNDLE_PATH $ACCOUNT

    # Create a GitHub release
    echo
    echo "Releasing aws-dd-forwarder-${FORWARDER_VERSION} to GitHub..."
    go get github.com/github/hub
    hub release create -a $BUNDLE_PATH -m "aws-dd-forwarder-${FORWARDER_VERSION}" aws-dd-forwarder-${FORWARDER_VERSION}
    
    # Upload the prod layers
    echo
    echo "Uploading layers"
    ./tools/publish_prod.sh $LAYER_VERSION $FORWARDER_VERSION

    # Set vars for use in the installation test
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder/latest.yaml"
    FORWARDER_SOURCE_URL="https://github.com/DataDog/datadog-serverless-functions/releases/download/aws-dd-forwarder-${FORWARDER_VERSION}/aws-dd-forwarder-${FORWARDER_VERSION}.zip'"
else
    # Build the bundle
    echo
    echo "Building the Forwarder bundle..."
    ./tools/build_bundle.sh $FORWARDER_VERSION

    # Sign the bundle
    echo
    echo "Signing the Forwarder bundle..."
    aws-login ./tools/sign_bundle.sh $BUNDLE_PATH $ACCOUNT

    # Upload the bundle to S3 instead of GitHub for a sandbox release
    echo
    echo "Uploading non-public sandbox version of Forwarder to S3..."
    aws-login aws s3 cp $BUNDLE_PATH s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${FORWARDER_VERSION}.zip
    
    # Upload the sandbox layers
    echo
    echo "Uploading layers"
    ./tools/publish_sandbox.sh $LAYER_VERSION $FORWARDER_VERSION

    # Set vars for use in the installation test
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder-staging/latest.yaml"
    FORWARDER_SOURCE_URL="s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${FORWARDER_VERSION}.zip"
fi

# Upload the CloudFormation template to the S3 bucket
echo
echo "Uploading template.yaml to s3://${BUCKET}/aws/forwarder/${FORWARDER_VERSION}.yaml"

if [ "$ACCOUNT" = "prod" ] ; then
    aws-login aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/${FORWARDER_VERSION}.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
    aws-login aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/latest.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
else
    aws-login aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder-staging/${FORWARDER_VERSION}.yaml
    aws-login aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder-staging/latest.yaml
fi

echo "Done uploading the CloudFormation template!"
echo
echo "Here is the CloudFormation quick launch URL:"
echo "https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=datadog-serverless&templateURL=${TEMPLATE_URL}"
echo
echo "Forwarder release process complete!"
if [ "$ACCOUNT" = "prod" ] ; then
    echo "Don't forget to add release notes in GitHub!"
fi

