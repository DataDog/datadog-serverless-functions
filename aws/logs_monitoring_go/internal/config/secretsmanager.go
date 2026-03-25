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
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

type SecretsManagerAPIClient interface {
	GetSecretValue(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error)
}

func (c *Config) createSecretsManagerAPIClient(ctx context.Context, awsCfg aws.Config) (SecretsManagerAPIClient, error) {
	resolver := secretsmanager.NewDefaultEndpointResolverV2()
	params := secretsmanager.EndpointParameters{
		Region:  aws.String(awsCfg.Region),
		UseFIPS: aws.Bool(c.UseFIPS),
	}

	endpoint, err := resolver.ResolveEndpoint(ctx, params)
	if err != nil && c.UseFIPS {
		slog.Warn("FIPS endpoint not available, falling back to standard endpoint", slog.String("service", "secretsmanager"), slog.String("region", awsCfg.Region))
		params.UseFIPS = aws.Bool(false)
		endpoint, err = resolver.ResolveEndpoint(ctx, params)
	}
	if err != nil {
		return nil, fmt.Errorf("resolve endpoint: %w", err)
	}

	return secretsmanager.NewFromConfig(awsCfg, func(o *secretsmanager.Options) {
		o.BaseEndpoint = aws.String(endpoint.URI.String())
	}), nil
}

func resolveFromSecretsManager(ctx context.Context, client SecretsManagerAPIClient, arn string) (string, error) {
	result, err := client.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(arn),
	})
	if err != nil {
		return "", fmt.Errorf("fetching secret %s: %w", arn, err)
	}
	if result.SecretString == nil {
		return "", fmt.Errorf("secret %s has no string value", arn)
	}

	return strings.TrimSpace(*result.SecretString), nil
}
