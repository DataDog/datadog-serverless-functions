// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=ssm.go -package=sdkclient -destination=ssm_mockgen.go

import (
	"context"
	"fmt"
	"strings"
	"sync"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
)

type SSM interface {
	GetParameter(ctx context.Context, params *ssm.GetParameterInput, optFns ...func(*ssm.Options)) (*ssm.GetParameterOutput, error)
}

var getSSM = sync.OnceValues(func() (SSM, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return ssm.NewFromConfig(cfg), nil
})

func ResolveFromSSM(ctx context.Context, name string) (string, error) {
	ssmClient, err := getSSM()
	if err != nil {
		return "", err
	}
	return FetchSSMParameter(ctx, ssmClient, name)
}

func FetchSSMParameter(ctx context.Context, ssmClient SSM, name string) (string, error) {
	result, err := ssmClient.GetParameter(ctx, &ssm.GetParameterInput{
		Name:           aws.String(name),
		WithDecryption: aws.Bool(true),
	})
	if err != nil {
		return "", fmt.Errorf("fetching parameter `%s`: %w", name, err)
	}

	if result.Parameter == nil {
		return "", fmt.Errorf("parameter `%s` has no value", name)
	}

	if result.Parameter.Value == nil {
		return "", fmt.Errorf("parameter `%s` has no string value", name)
	}

	return strings.TrimSpace(*result.Parameter.Value), nil
}
