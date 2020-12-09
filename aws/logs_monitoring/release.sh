#!/bin/bash

# Usage: ./release.sh <Desired Version> <Account [sandbox|prod]>

set -e

# Read the current version
CURRENT_VERSION=$(grep -o 'Version: \d\+\.\d\+\.\d\+' template.yaml | cut -d' ' -f2)

# Read the desired version
if [ -z "$1" ]; then
    echo "ERROR: You must specify a desired version number"
    exit 1
elif [[ ! $1 =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
    echo "ERROR: You must use a semantic version (e.g. 3.1.4)"
    exit 1
else
    VERSION=$1
fi

BUNDLE_PATH=".forwarder/aws-dd-forwarder-${VERSION}.zip"

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
    BUCKET="datadog-cloudformation-template-sandbox"
fi
if [ "$ACCOUNT" = "prod" ]; then
    BUCKET="datadog-cloudformation-template"
fi

# Validate identity
aws sts get-caller-identity

# Validate the template
echo
echo "Validating template.yaml..."
aws cloudformation validate-template --template-body file://template.yaml

if [ "$ACCOUNT" = "prod" ] ; then

    if [[ ! $(./tools/semver.sh "$VERSION" "$CURRENT_VERSION") > 0 ]]; then
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
    read -p "About to bump the version from ${CURRENT_VERSION} to ${VERSION}, create a release aws-dd-forwarder-${VERSION} on GitHub and upload the template.yaml to s3://${BUCKET}/aws/forwarder/${VERSION}.yaml. Continue (y/n)?" CONT
    if [ "$CONT" != "y" ]; then
        echo "Exiting..."
        exit 1
    fi

    # Get the latest code
    git pull origin master

    # Bump version number in settings.py and template.yml
    echo "Bumping the version number to ${VERSION}..."
    perl -pi -e "s/DD_FORWARDER_VERSION = \"[0-9\.]+/DD_FORWARDER_VERSION = \"${VERSION}/g" settings.py
    perl -pi -e "s/Version: [0-9\.]+/Version: ${VERSION}/g" template.yaml

    # Commit version number changes to git
    echo "Committing version number change..."
    git add settings.py template.yaml
    git commit -m "Bump version from ${CURRENT_VERSION} to ${VERSION}"
    git push origin master

    # Build the bundle
    echo
    echo "Building the Forwarder bundle..."
    ./tools/build_bundle.sh "${VERSION}"

    # Sign the bundle
    echo
    echo "Signing the Forwarder bundle..."
    ./tools/sign_bundle.sh $BUNDLE_PATH $ACCOUNT

    # Create a GitHub release
    echo
    echo "Releasing aws-dd-forwarder-${VERSION} to GitHub..."
    go get github.com/github/hub
    hub release create -a $BUNDLE_PATH -m "aws-dd-forwarder-${VERSION}" aws-dd-forwarder-${VERSION}

    # Set vars for use in the installation test
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder/latest.yaml"
    FORWARDER_SOURCE_URL="https://github.com/DataDog/datadog-serverless-functions/releases/download/aws-dd-forwarder-${VERSION}/aws-dd-forwarder-${VERSION}.zip'"
else
    # Build the bundle
    echo
    echo "Building the Forwarder bundle..."
    ./tools/build_bundle.sh $VERSION

    # Sign the bundle
    echo
    echo "Signing the Forwarder bundle..."
    ./tools/sign_bundle.sh $BUNDLE_PATH $ACCOUNT

    # Upload the bundle to S3 instead of GitHub for a sandbox release
    echo
    echo "Uploading non-public sandbox version of Forwarder to S3..."
    aws s3 cp $BUNDLE_PATH s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${VERSION}.zip

    # Set vars for use in the installation test
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder-staging/latest.yaml"
    FORWARDER_SOURCE_URL="s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${VERSION}.zip"
fi

# Upload the CloudFormation template to the S3 bucket
echo
echo "Uploading template.yaml to s3://${BUCKET}/aws/forwarder/${VERSION}.yaml"

if [ "$ACCOUNT" = "prod" ] ; then
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/${VERSION}.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/latest.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
else
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder-staging/${VERSION}.yaml
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder-staging/latest.yaml
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

