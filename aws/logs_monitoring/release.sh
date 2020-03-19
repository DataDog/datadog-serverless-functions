#!/bin/bash

# Usage: ./release.sh <S3_Bucket> <Version>

set -e

# Read the S3 bucket
if [ -z "$1" ]; then
    echo "Must specify a S3 bucket to publish the template"
    exit 1
else
    BUCKET=$1
fi

# Read the current version
CURRENT_VERSION=$(grep -o 'Version: \d\+\.\d\+\.\d\+' template.yaml | cut -d' ' -f2)

# Read the desired version
if [ -z "$2" ]; then
    echo "Must specify a desired version number"
    exit 1
elif [[ ! $2 =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
    echo "Must use a semantic version, e.g., 3.1.4"
    exit 1
else
    VERSION=$2
fi

# Do a production release (default is staging) - useful for developers
if [[ $# -eq 3 ]] && [[ $3 = "--prod" ]]; then
    PROD_RELEASE=true
else
    PROD_RELEASE=false
fi

# Validate identity
aws sts get-caller-identity

# Validate the template
echo "Validating template.yaml"
aws cloudformation validate-template --template-body file://template.yaml

if [ "$PROD_RELEASE" = true ] ; then

    if [[ ! $(./tools/semver.sh "$VERSION" "$CURRENT_VERSION") > 0 ]]; then
        echo "Must use a version greater than the current ($CURRENT_VERSION)"
        exit 1
    fi
    # Make sure we are on master
    BRANCH=$(git rev-parse --abbrev-ref HEAD)
    if [ $BRANCH != "master" ]; then
        echo "Not on master, aborting"
        exit 1
    fi

    # Confirm to proceed
    read -p "About to bump the version from ${CURRENT_VERSION} to ${VERSION}, create a release aws-dd-forwarder-${VERSION} on Github and upload the template.yaml to s3://${BUCKET}/aws/forwarder/${VERSION}.yaml. Continue (y/n)?" CONT
    if [ "$CONT" != "y" ]; then
        echo "Exiting"
        exit 1
    fi

    # Get the latest code
    git pull origin master

    # Bump version number
    echo "Bumping the current version number to the desired"
    perl -pi -e "s/DD_FORWARDER_VERSION = \"${CURRENT_VERSION}/DD_FORWARDER_VERSION = \"${VERSION}/g" lambda_function.py
    perl -pi -e "s/Version: ${CURRENT_VERSION}/Version: ${VERSION}/g" template.yaml

    # Commit version number changes to git
    git add lambda_function.py template.yaml README.md
    git commit -m "Bump version from ${CURRENT_VERSION} to ${VERSION}"
    git push origin master

    # Create a github release
    echo "Release aws-dd-forwarder-${VERSION} to github"
    go get github.com/github/hub
    rm -f aws-dd-forwarder-*.zip
    zip -r aws-dd-forwarder-${VERSION}.zip . \
        --exclude=*tools* \
        --exclude=*tests* \
        --exclude=*.DS_Store* \
        --exclude=*.gitignore*
    hub release create -a aws-dd-forwarder-${VERSION}.zip -m "aws-dd-forwarder-${VERSION}" aws-dd-forwarder-${VERSION}
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder/latest.yaml"
    FORWARDER_SOURCE_URL="https://github.com/DataDog/datadog-serverless-functions/releases/download/aws-dd-forwarder-${VERSION}/aws-dd-forwarder-${VERSION}.zip'"
else
    echo "About to release non-public staging version of forwarder, upload aws-dd-forwarder-${VERSION} to s3, and upload the template.yaml to s3://${BUCKET}/aws/forwarder-staging/${VERSION}.yaml"
    # Upload to s3 instead of github
    rm -f aws-dd-forwarder-*.zip
    zip -r aws-dd-forwarder-${VERSION}.zip . \
        --exclude=*tools* \
        --exclude=*tests* \
        --exclude=*.DS_Store* \
        --exclude=*.gitignore*
    aws s3 cp aws-dd-forwarder-${VERSION}.zip s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${VERSION}.zip
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder-staging/latest.yaml"
    FORWARDER_SOURCE_URL="s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${VERSION}.zip"
fi

# Upload the template to the S3 bucket
echo "Uploading template.yaml to s3://${BUCKET}/aws/forwarder/${VERSION}.yaml"

if [ "$PROD_RELEASE" = true ] ; then
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/${VERSION}.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/latest.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
else
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder-staging/${VERSION}.yaml
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder-staging/latest.yaml
fi

echo "Done uploading the template, and here is the CloudFormation quick launch URL"
echo "https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=datadog-serverless&templateURL=${TEMPLATE_URL}"

echo "Done!"
