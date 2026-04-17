// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"context"
	"errors"

	"github.com/aws/aws-lambda-go/lambdacontext"
)

var ErrLambdaContextMissing = errors.New("lambda context not found")

type Metadata struct {
	ARN     string `json:"invoked_function_arn"`
	Version string `json:"function_version,omitempty"`
}

func GetMetadata(ctx context.Context) (Metadata, error) {
	var metadata Metadata

	if lambdacontext.FunctionVersion != "$LATEST" {
		metadata.Version = lambdacontext.FunctionVersion
	}

	lc, ok := lambdacontext.FromContext(ctx)
	if !ok {
		return Metadata{}, ErrLambdaContextMissing
	}

	metadata.ARN = lc.InvokedFunctionArn

	return metadata, nil
}
