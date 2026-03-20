// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"crypto/tls"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
)

const (
	httpClientTimeout  = 10 * time.Second
	maxRetries         = 5
	retryBackoffFactor = 1 * time.Second
)

type resolveOptions struct {
	AWSCfg aws.Config
	Value  string
}

type apiKeyResolver func(ctx context.Context, opts resolveOptions) (string, error)

var retryableStatusCodes = map[int]bool{
	429: true,
	500: true,
	502: true,
	503: true,
	504: true,
}

var resolvers = []struct {
	envVar  string
	resolve apiKeyResolver
}{
	{"DD_API_KEY_SECRET_ARN", resolveFromSecretsManager},
	{"DD_API_KEY_SSM_NAME", resolveFromSSM},
	{"DD_KMS_API_KEY", resolveFromKMS},
	{"DD_API_KEY", resolveFromEnv},
}

func (c *Config) resolveAPIKey(ctx context.Context) error {
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx,
		awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(httpClientTimeout)),
	)

	if err != nil {
		return fmt.Errorf("loading AWS config: %w", err)
	}

	for _, resolver := range resolvers {
		if v, ok := os.LookupEnv(resolver.envVar); ok {
			slog.Debug("resolving API key", "source", resolver.envVar)
			key, err := resolver.resolve(ctx, resolveOptions{
				AWSCfg: awsCfg,
				Value:  v,
			})
			if err != nil {
				return fmt.Errorf("resolving API key from %s: %w", resolver.envVar, err)
			}
			c.APIKey = key
			return nil
		}
	}
	return errors.New("no API key configured: set DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME, DD_KMS_API_KEY, or DD_API_KEY. See: https://docs.datadoghq.com/serverless/forwarder/")
}

// Note: the API key verification could fail (e.g. Datadog verification endpoint or network problem)
// Instead of failing the whole lambda at startup, it should run up to the log sending part and verify the
// key at this moment, adding the run to the future retry logic in such case.
// The method may disappear in the future.
func (c *Config) validateAPIKey() error {
	if c.APIKey == "" || c.APIKey == "<YOUR_DATADOG_API_KEY>" {
		return errors.New("missing Datadog API key. Set DD_API_KEY environment variable. See: https://docs.datadoghq.com/serverless/forwarder/")
	}

	if len(c.APIKey) != 32 {
		return fmt.Errorf("invalid Datadog API key format: expected 32 characters, got %d. Verify your API key at https://app.%s/organization-settings/api-keys", len(c.APIKey), c.Site)
	}

	slog.Debug("validating Datadog API key")

	client := &http.Client{
		Timeout: httpClientTimeout,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				InsecureSkipVerify: c.SkipSSLValidation,
			},
		},
	}

	url := fmt.Sprintf("%s/api/v1/validate?api_key=%s", c.APIURL, c.APIKey)

	var lastErr error
	var lastStatus int
	for attempt := range maxRetries {
		resp, err := client.Get(url)
		if err != nil {
			lastErr = err
			slog.Debug("API key validation request failed, retrying", "attempt", attempt+1, "error", err)
			time.Sleep(retryBackoffFactor * time.Duration(1<<attempt))
			continue
		}
		resp.Body.Close()

		if resp.StatusCode >= 200 && resp.StatusCode < 300 {
			return nil
		}

		if !retryableStatusCodes[resp.StatusCode] {
			slog.Warn("API key validation failed. Verify your API key is correct and DD_SITE matches your Datadog account region. See: https://docs.datadoghq.com/getting_started/site/",
				"status", resp.StatusCode,
				"site", c.Site,
			)
			return nil
		}

		lastStatus = resp.StatusCode
		slog.Debug("API key validation returned retryable status, retrying", "attempt", attempt+1, "status", resp.StatusCode)
		time.Sleep(retryBackoffFactor * time.Duration(1<<attempt))
	}

	if lastErr != nil {
		slog.Warn("API key validation failed after retries, continuing anyway", "attempts", maxRetries, "error", lastErr)
	} else {
		slog.Warn("API key validation failed after retries. Verify your API key is correct and DD_SITE matches your Datadog account region. See: https://docs.datadoghq.com/getting_started/site/",
			"attempts", maxRetries,
			"lastStatus", lastStatus,
			"site", c.Site,
		)
	}

	return nil
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
	return opts.Value, nil
}
