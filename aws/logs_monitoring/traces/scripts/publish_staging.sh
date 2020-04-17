#!/bin/bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2019 Datadog, Inc.

./scripts/build_layers.sh
aws-vault exec demo-account-admin -- ./scripts/publish_layers.sh us-east-1