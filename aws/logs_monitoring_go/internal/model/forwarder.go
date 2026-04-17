// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"context"
	"log/slog"

	"github.com/aws/aws-lambda-go/lambdacontext"
)

type ForwarderMetadata struct {
	ARN     string `json:"invoked_function_arn"`
	Version string `json:"function_version,omitempty"`
}

func GetForwarderMetadata(ctx context.Context) ForwarderMetadata {
	var metadata ForwarderMetadata

	if lambdacontext.FunctionVersion != "$LATEST" {
		metadata.Version = lambdacontext.FunctionVersion
	}

	if lc, ok := lambdacontext.FromContext(ctx); ok {
		metadata.ARN = lc.InvokedFunctionArn
	} else {
		slog.Warn("failed to load lambda context, this should not happen in production. The code is either not running from AWS Lambda or context is broken.")
	}

	return metadata
}
