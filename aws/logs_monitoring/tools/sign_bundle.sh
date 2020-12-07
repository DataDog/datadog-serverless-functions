#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2020 Datadog, Inc.

# Usage: ./sign_bundle.sh <Bundle Path> <Account [sandbox|prod]>

set -e

SIGNING_PROFILE_NAME="DatadogLambdaSigningProfile"

# Get bundle path from arguments
if [ -z "$1" ]; then
    echo "ERROR: You must pass a bundle path to sign"
    exit 1
fi
BUNDLE_LOCAL_PATH=$1

# Check account parameter
VALID_ACCOUNTS=("sandbox" "prod")
if [ -z "$2" ]; then
    echo "ERROR: You must pass an account parameter to sign the bundle"
    exit 1
fi
if [[ ! "${VALID_ACCOUNTS[@]}" =~ $2 ]]; then
    echo "ERROR: The account parameter was invalid. Please choose sandbox or prod."
    exit 1
fi
if [ "$2" = "sandbox" ]; then
    REGION="sa-east-1"
    S3_BUCKET_NAME="dd-lambda-signing-bucket-sandbox"
fi
if [ "$2" = "prod" ]; then
    REGION="us-east-1"
    S3_BUCKET_NAME="dd-lambda-signing-bucket"
fi

echo

# Upload the bundle to S3 for signing
echo "Uploading bundle to S3 for signing..."
UUID=$(uuidgen)
S3_UNSIGNED_ZIP_KEY="${UUID}.zip"
S3_UNSIGNED_ZIP_URI="s3://${S3_BUCKET_NAME}/${S3_UNSIGNED_ZIP_KEY}"
aws s3 cp $BUNDLE_LOCAL_PATH $S3_UNSIGNED_ZIP_URI

# Start a signing job
echo "Starting the signing job..."
SIGNING_JOB_ID=$(aws signer start-signing-job \
    --source "s3={bucketName=${S3_BUCKET_NAME},key=${S3_UNSIGNED_ZIP_KEY},version=null}" \
    --destination "s3={bucketName=${S3_BUCKET_NAME}}" \
    --profile-name $SIGNING_PROFILE_NAME \
    --region $REGION \
    | jq -r '.jobId'\
)

# Wait for the signing job to complete
echo "Waiting for the signing job to complete..."
SECONDS_WAITED_SO_FAR=0
while :
do
    sleep 3
    SECONDS_WAITED_SO_FAR=$((SECONDS_WAITED_SO_FAR + 3))
    
    SIGNING_JOB_DESCRIPTION=$(aws signer describe-signing-job \
        --job-id $SIGNING_JOB_ID \
        --region $REGION\
    )
    SIGNING_JOB_STATUS=$(echo $SIGNING_JOB_DESCRIPTION | jq -r '.status')
    SIGNING_JOB_STATUS_REASON=$(echo $SIGNING_JOB_DESCRIPTION | jq -r '.statusReason')

    if [ $SIGNING_JOB_STATUS = "Succeeded" ]; then
        echo "Signing job succeeded!"
        break
    fi

    if [ $SIGNING_JOB_STATUS = "Failed" ]; then
        echo "ERROR: Signing job failed"
        echo $SIGNING_JOB_STATUS_REASON
        exit 1
    fi

    if [ $SECONDS_WAITED_SO_FAR -ge 60 ]; then
        echo "ERROR: Timed out waiting for the signing job to complete"
        exit 1
    fi

    echo "Signing job still in progress..."
done

# Download the signed ZIP, overwriting the original ZIP
echo "Replacing the local bundle with the bundle from S3..."
S3_SIGNED_ZIP_KEY="${SIGNING_JOB_ID}.zip"
S3_SIGNED_ZIP_URI="s3://${S3_BUCKET_NAME}/${S3_SIGNED_ZIP_KEY}"
aws s3 cp $S3_SIGNED_ZIP_URI $BUNDLE_LOCAL_PATH

# Delete the signed and unsigned ZIPs in S3
echo "Cleaning up the S3 bucket..."
aws s3api delete-object --bucket $S3_BUCKET_NAME --key $S3_UNSIGNED_ZIP_KEY
aws s3api delete-object --bucket $S3_BUCKET_NAME --key $S3_SIGNED_ZIP_KEY

echo
echo "Successfully signed the bundle!"
echo