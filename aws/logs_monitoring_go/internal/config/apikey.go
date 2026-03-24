// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"time"

	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
)

var (
	ErrMissingAPIKey = errors.New("missing Datadog API key")
	ErrInvalidAPIKey = errors.New("invalid Datadog API key format")
)

const (
	httpClientTimeout = 3 * time.Second
)

func (c *Config) resolveAPIKey(ctx context.Context) error {
	awsCfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(httpClientTimeout)))
	if err != nil {
		return fmt.Errorf("loading AWS config: %w", err)
	}

	if v, ok := os.LookupEnv("DD_API_KEY_SECRET_ARN"); ok {
		return c.resolveFromSecretsManager(ctx, awsCfg, v)
	}

	if v, ok := os.LookupEnv("DD_API_KEY_SSM_NAME"); ok {
		return c.resolveFromSSM(ctx, awsCfg, v)
	}

	if v, ok := os.LookupEnv("DD_KMS_API_KEY"); ok {
		return c.resolveFromKMS(ctx, awsCfg, v)
	}

	return errors.New("no API key configured: set DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME or DD_KMS_API_KEY. See: https://docs.datadoghq.com/serverless/forwarder/")
}

func (c *Config) validateAPIKey(ctx context.Context) error {
	if c.APIKey == "" {
		return fmt.Errorf("%w: set DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME or DD_KMS_API_KEY. See: https://docs.datadoghq.com/serverless/forwarder/", ErrMissingAPIKey)
	}

	if len(c.APIKey) != 32 {
		return fmt.Errorf("%w: expected 32 characters, got %d. Verify your API key at https://app.%s/organization-settings/api-keys", ErrInvalidAPIKey, len(c.APIKey), c.Site)
	}

	slog.Debug("validating Datadog API key")

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.APIURL+"/api/v1/validate", nil)
	if err != nil {
		slog.Warn("failed to build API key validation request", slog.String("error", err.Error()))
		return nil
	}
	req.Header.Set("DD-API-KEY", c.APIKey)

	client := &http.Client{Timeout: httpClientTimeout}
	resp, err := client.Do(req)
	if err != nil {
		slog.Warn("failed to validate API key", slog.String("error", err.Error()))
		return nil
	}
	defer func() {
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
	}()

	if resp.StatusCode == http.StatusForbidden {
		slog.Warn("invalid Datadog API key", slog.String("url", "https://app."+c.Site+"/organization-settings/api-keys"))
	} else if resp.StatusCode != http.StatusOK {
		slog.Warn("unexpected response from validation endpoint", slog.String("status", resp.Status))
	}

	return nil
}
