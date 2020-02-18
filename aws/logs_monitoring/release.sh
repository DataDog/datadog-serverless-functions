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

# Get the latest code
git checkout master
git pull origin master

# Read the current version
CURRENT_VERSION=$(grep -o 'Version: \d\+\.\d\+\.\d\+' template.yaml | cut -d' ' -f2)

# Read the desired version
if [ -z "$2" ]; then
    echo "Must specify a desired version number"
    exit 1
elif [[ ! $2 =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
    echo "Must use a semantic version, e.g., 3.1.4"
    exit 1
elif [[ ! "$2" > "$CURRENT_VERSION" ]]; then
    echo "Must use a version greater than the current ($CURRENT_VERSION)"
    exit 1
else
    VERSION=$2
fi

# Make the template private (default is public) - useful for developers
if [[ $# -eq 3 ]] && [[ $3 = "--private" ]]; then
    PRIVATE_TEMPLATE=true
else
    PRIVATE_TEMPLATE=false
fi

# Validate the template
echo "Validating template.yaml"
aws cloudformation validate-template --template-body file://template.yaml

# Confirm to proceed
read -p "About to bump the version from ${CURRENT_VERSION} to ${VERSION}, create a release aws-dd-forwarder-${VERSION} on Github and upload the template.yaml to s3://${BUCKET}/aws/forwarder/${VERSION}.yaml. Continue (y/n)?" CONT
if [ "$CONT" != "y" ]; then
  echo "Exiting"
  exit 1
fi

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
zip -r aws-dd-forwarder-${VERSION}.zip .
hub release create -a aws-dd-forwarder-${VERSION}.zip -m "aws-dd-forwarder-${VERSION}" aws-dd-forwarder-${VERSION}

# Upload the template to the S3 bucket
echo "Uploading template.yaml to s3://${BUCKET}/aws/forwarder/${VERSION}.yaml"
if [ "$PRIVATE_TEMPLATE" = true ] ; then
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/${VERSION}.yaml
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/latest.yaml
else
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/${VERSION}.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
    aws s3 cp template.yaml s3://${BUCKET}/aws/forwarder/latest.yaml \
        --grants read=uri=http://acs.amazonaws.com/groups/global/AllUsers
fi
echo "Done uploading the template, and here is the CloudFormation quick launch URL"
echo "https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=datadog-serverless&templateURL=https://${BUCKET}.s3.amazonaws.com/aws/forwarder/latest.yaml"

echo "Done!"
