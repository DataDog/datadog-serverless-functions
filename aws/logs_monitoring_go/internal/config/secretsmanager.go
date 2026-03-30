// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

//go:generate go tool mockgen -source=secretsmanager.go -package=config -destination=secretsmanager_mockgen.go

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

type SecretsManagerAPIClient interface {
	GetSecretValue(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error)
}

func (c *Config) resolveAPIKeyFromSecretsManager(ctx context.Context, arn string) (string, error) {
	client, err := c.createSecretsManagerAPIClient(ctx)
	if err != nil {
		return "", err
	}
	return fetchSecret(ctx, client, arn)
}

func (c *Config) createSecretsManagerAPIClient(ctx context.Context) (SecretsManagerAPIClient, error) {
	cfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(httpClientTimeout)))
	if err != nil {
		return nil, err
	}

	resolver := secretsmanager.NewDefaultEndpointResolverV2()
	params := secretsmanager.EndpointParameters{
		Region:  aws.String(cfg.Region),
		UseFIPS: aws.Bool(c.UseFIPS),
	}

	endpoint, err := resolver.ResolveEndpoint(ctx, params)
	if err != nil && c.UseFIPS {
		slog.Warn("FIPS endpoint not available, falling back to standard endpoint", slog.String("service", "secretsmanager"), slog.String("region", cfg.Region))
		params.UseFIPS = aws.Bool(false)
		endpoint, err = resolver.ResolveEndpoint(ctx, params)
	}
	if err != nil {
		return nil, fmt.Errorf("resolve endpoint: %w", err)
	}

	return secretsmanager.NewFromConfig(cfg, func(o *secretsmanager.Options) {
		o.BaseEndpoint = aws.String(endpoint.URI.String())
	}), nil
}

func fetchSecret(ctx context.Context, client SecretsManagerAPIClient, arn string) (string, error) {
	result, err := client.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(arn),
	})
	if err != nil {
		return "", fmt.Errorf("fetching secret `%s`: %w", arn, err)
	}

	if result.SecretString == nil {
		return "", fmt.Errorf("secret `%s` has no string value", arn)
	}

	return strings.TrimSpace(*result.SecretString), nil
}
