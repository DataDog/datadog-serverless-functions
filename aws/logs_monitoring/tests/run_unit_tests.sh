#!/bin/bash

export DD_API_KEY=11111111111111111111111111111111
export DD_ADDITIONAL_TARGET_LAMBDAS=ironmaiden,megadeth
export DD_STORE_FAILED_EVENTS="true"
export DD_S3_BUCKET_NAME=dd-s3-bucket
python3 -m unittest discover .
