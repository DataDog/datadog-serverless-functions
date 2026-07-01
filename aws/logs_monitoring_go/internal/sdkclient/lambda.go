// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=lambda.go -package=$GOPACKAGE -destination=lambda_mockgen.go

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/lambda"
	"github.com/aws/aws-sdk-go-v2/service/lambda/types"
)

var getLambda = sync.OnceValues(func() (Lambda, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return lambda.NewFromConfig(cfg), nil
})

type Lambda interface {
	Invoke(ctx context.Context, params *lambda.InvokeInput, optFns ...func(*lambda.Options)) (*lambda.InvokeOutput, error)
}

func InvokeTargets(ctx context.Context, targets []string, event json.RawMessage) error {
	client, err := getLambda()
	if err != nil {
		return err
	}
	return invokeTargets(ctx, client, targets, event)
}

func invokeTargets(ctx context.Context, lambdaClient Lambda, targets []string, event json.RawMessage) error {
	for _, target := range targets {
		_, err := lambdaClient.Invoke(ctx, &lambda.InvokeInput{
			FunctionName:   aws.String(target),
			InvocationType: types.InvocationTypeEvent,
			Payload:        event,
		})
		if err != nil {
			return fmt.Errorf("invoke %q: %w", target, err)
		}
	}
	return nil
}
