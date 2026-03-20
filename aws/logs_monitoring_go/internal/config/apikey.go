// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
)

const (
	TIMEOUT = 5
)

type resolveOptions struct {
	AWSCfg  aws.Config
	Value   string
	UseFIPS bool
}

type apiKeyResolver func(ctx context.Context, opts resolveOptions) (string, error)

var resolvers = []struct {
	envVar  string
	resolve apiKeyResolver
}{
	{"DD_API_KEY_SECRET_ARN", resolveFromSecretsManager},
	{"DD_API_KEY_SSM_NAME", resolveFromSSM},
	{"DD_KMS_API_KEY", resolveFromKMS},
	{"DD_API_KEY", resolveFromEnv},
}

func resolveAPIKey(ctx context.Context, useFIPS bool) (string, error) {
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx,
		awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(time.Second*TIMEOUT)),
	)

	if err != nil {
		return "", fmt.Errorf("loading AWS config: %w", err)
	}

	for _, resolver := range resolvers {
		if v, ok := os.LookupEnv(resolver.envVar); ok {
			slog.Debug("resolving API key", "source", resolver.envVar)
			resolver.resolve(ctx, resolveOptions{
				AWSCfg:  awsCfg,
				Value:   v,
				UseFIPS: useFIPS,
			})
		}
	}
	return "", errors.New("no API key configured: set DD_API_KEY, DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME, or DD_KMS_API_KEY. See: https://docs.datadoghq.com/serverless/forwarder/")
}

func resolveFromSecretsManager(ctx context.Context, opts resolveOptions) (string, error) {
	return "", nil
}

func resolveFromSSM(ctx context.Context, opts resolveOptions) (string, error) {
	return "", nil
}

func resolveFromKMS(ctx context.Context, opts resolveOptions) (string, error) {
	return "", nil
}

func resolveFromEnv(ctx context.Context, opts resolveOptions) (string, error) {
	// if len(opts.Value) != 32 {
	// 	return "", fmt.Errorf("invalid datadog api key format")
	// }

	// client := &http.Client{
	// 	Timeout: TIMEOUT * time.Second,
	// 	Transport: &http.Transport{
	// 		TLSClientConfig: &tls.Config{
	// 			InsecureSkipVerify: skipSSLValidation,
	// 		},
	// 	},
	// }

	// res, err := http.Get()
	// if err != nil {

	// }

	return opts.Value, nil
}

func validateAPIKey(cfg Config) {

}
