// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package client

//go:generate go tool mockgen -source=ssm.go -package=client -destination=ssm_mockgen.go

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
)

type SSM interface {
	GetParameter(ctx context.Context, params *ssm.GetParameterInput, optFns ...func(*ssm.Options)) (*ssm.GetParameterOutput, error)
}

func NewSSM(ctx context.Context, useFIPS bool) (SSM, error) {
	cfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(timeout)))
	if err != nil {
		return nil, err
	}

	resolver := ssm.NewDefaultEndpointResolverV2()
	params := ssm.EndpointParameters{
		Region:  aws.String(cfg.Region),
		UseFIPS: aws.Bool(useFIPS),
	}

	endpoint, err := resolver.ResolveEndpoint(ctx, params)
	if err != nil && useFIPS {
		slog.Warn("FIPS endpoint not available, falling back to standard endpoint", slog.String("service", "ssm"), slog.String("region", cfg.Region))
		params.UseFIPS = aws.Bool(false)
		endpoint, err = resolver.ResolveEndpoint(ctx, params)
	}
	if err != nil {
		return nil, fmt.Errorf("resolve endpoint: %w", err)
	}

	return ssm.NewFromConfig(cfg, func(o *ssm.Options) {
		o.BaseEndpoint = aws.String(endpoint.URI.String())
	}), nil
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
