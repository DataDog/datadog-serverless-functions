// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

type SecretsManager interface {
	GetSecretValue(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error)
}

// used for mocking purpose
var getSecretsManagerClient = func(cfg aws.Config, optFns ...func(*secretsmanager.Options)) SecretsManager {
	return secretsmanager.NewFromConfig(cfg, optFns...)
}

func (c *Config) resolveFromSecretsManager(ctx context.Context, awsCfg aws.Config, arn string) error {
	slog.Debug("resolving API key from Secrets Manager")

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
		return fmt.Errorf("resolve endpoint: %w", err)
	}

	client := getSecretsManagerClient(awsCfg, func(o *secretsmanager.Options) {
		o.BaseEndpoint = aws.String(endpoint.URI.String())
	})

	result, err := client.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(arn),
	})
	if err != nil {
		return fmt.Errorf("fetching secret %s: %w", arn, err)
	}

	if result.SecretString == nil {
		return fmt.Errorf("secret %s has no string value", arn)
	}
	c.APIKey = strings.TrimSpace(*result.SecretString)
	return nil
}
