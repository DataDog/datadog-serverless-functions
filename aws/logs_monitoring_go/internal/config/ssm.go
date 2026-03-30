// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

//go:generate go tool mockgen -source=ssm.go -package=config -destination=ssm_mockgen.go

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

type SSMAPIClient interface {
	GetParameter(ctx context.Context, params *ssm.GetParameterInput, optFns ...func(*ssm.Options)) (*ssm.GetParameterOutput, error)
}

func (c *Config) resolveAPIKeyFromSSM(ctx context.Context, name string) (string, error) {
	client, err := c.createSSMAPIClient(ctx)
	if err != nil {
		return "", err
	}
	return fetchSSMParameter(ctx, client, name)
}

func (c *Config) createSSMAPIClient(ctx context.Context) (SSMAPIClient, error) {
	cfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(httpClientTimeout)))
	if err != nil {
		return nil, err
	}

	resolver := ssm.NewDefaultEndpointResolverV2()
	params := ssm.EndpointParameters{
		Region:  aws.String(cfg.Region),
		UseFIPS: aws.Bool(c.UseFIPS),
	}

	endpoint, err := resolver.ResolveEndpoint(ctx, params)
	if err != nil && c.UseFIPS {
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

func fetchSSMParameter(ctx context.Context, client SSMAPIClient, name string) (string, error) {
	result, err := client.GetParameter(ctx, &ssm.GetParameterInput{
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
