// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

//go:generate go tool mockgen -source=kms.go -package=config -destination=kms_mockgen.go

import (
	"context"
	"encoding/base64"
	"fmt"
	"log/slog"
	"strings"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/kms"
)

type KMSAPIClient interface {
	Decrypt(ctx context.Context, params *kms.DecryptInput, optFns ...func(*kms.Options)) (*kms.DecryptOutput, error)
}

func (c *Config) resolveAPIKeyFromKMS(ctx context.Context, ciphertext string) (string, error) {
	client, err := c.createKMSAPIClient(ctx)
	if err != nil {
		return "", err
	}
	return decryptKMSCiphertext(ctx, client, ciphertext)
}

func (c *Config) createKMSAPIClient(ctx context.Context) (KMSAPIClient, error) {
	cfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(httpClientTimeout)))
	if err != nil {
		return nil, err
	}

	resolver := kms.NewDefaultEndpointResolverV2()
	params := kms.EndpointParameters{
		Region:  aws.String(cfg.Region),
		UseFIPS: aws.Bool(c.UseFIPS),
	}

	endpoint, err := resolver.ResolveEndpoint(ctx, params)
	if err != nil && c.UseFIPS {
		slog.Warn("FIPS endpoint not available, falling back to standard endpoint", slog.String("service", "kms"), slog.String("region", cfg.Region))
		params.UseFIPS = aws.Bool(false)
		endpoint, err = resolver.ResolveEndpoint(ctx, params)
	}
	if err != nil {
		return nil, fmt.Errorf("resolve endpoint: %w", err)
	}

	return kms.NewFromConfig(cfg, func(o *kms.Options) {
		o.BaseEndpoint = aws.String(endpoint.URI.String())
	}), nil
}

func decryptKMSCiphertext(ctx context.Context, client KMSAPIClient, ciphertext string) (string, error) {
	decoded, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", fmt.Errorf("base64-decoding ciphertext: %w", err)
	}

	result, err := client.Decrypt(ctx, &kms.DecryptInput{
		CiphertextBlob: decoded,
	})
	if err != nil {
		return "", fmt.Errorf("decrypting KMS ciphertext: %w", err)
	}

	if result.Plaintext == nil {
		return "", fmt.Errorf("KMS decryption returned no plaintext")
	}

	return strings.TrimSpace(string(result.Plaintext)), nil
}
