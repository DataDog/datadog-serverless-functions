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
	"net/http"
	"os"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
)

var (
	ErrMissingAPIKey = errors.New("missing Datadog API key")
	ErrInvalidAPIKey = errors.New("invalid Datadog API key format")
)

type apiKeyResolver struct {
	envVar  string
	resolve func(ctx context.Context, value string) (string, error)
}

func (c *Config) ResolveAPIKey(ctx context.Context) error {
	resolvers := []apiKeyResolver{
		{"DD_API_KEY_SECRET_ARN", c.resolveAPIKeyFromSecretsManager},
		{"DD_API_KEY_SSM_NAME", c.resolveAPIKeyFromSSM},
		{"DD_KMS_API_KEY", c.resolveAPIKeyFromKMS},
	}

	for _, r := range resolvers {
		v, ok := os.LookupEnv(r.envVar)
		if !ok {
			continue
		}

		apiKey, err := r.resolve(ctx, v)
		if err != nil {
			return fmt.Errorf("resolving API key from %s: %w", r.envVar, err)
		}

		c.APIKey = apiKey
		return nil
	}

	return errors.New("no API key configured: set DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME or DD_KMS_API_KEY. See: https://docs.datadoghq.com/serverless/forwarder/")
}

func (c *Config) ValidateAPIKey(ctx context.Context) error {
	if c.APIKey == "" {
		return fmt.Errorf("set DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME or DD_KMS_API_KEY. See: https://docs.datadoghq.com/serverless/forwarder/: %w", ErrMissingAPIKey)
	}

	if len(c.APIKey) != 32 {
		return fmt.Errorf("expected 32 characters, got %d. Verify your API key at https://app.%s/organization-settings/api-keys: %w", len(c.APIKey), c.Site, ErrInvalidAPIKey)
	}

	slog.Debug("validating Datadog API key")

	ctx, cancel := context.WithTimeout(ctx, httpclient.RequestTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, c.APIURL+"/api/v1/validate", nil)
	if err != nil {
		return nil
	}

	req.Header.Set("DD-API-KEY", c.APIKey)

	resp, err := httpclient.Client.Do(req)
	if err != nil {
		slog.Warn("failed to validate API key", slog.Any("error", err))
		return nil
	}
	defer httpclient.DrainClose(resp)

	if resp.StatusCode == http.StatusForbidden {
		slog.Warn("invalid Datadog API key", slog.String("url", "https://app."+c.Site+"/organization-settings/api-keys"))
	} else if resp.StatusCode != http.StatusOK {
		slog.Warn("unexpected response from validation endpoint", slog.String("status", resp.Status))
	}

	return nil
}
