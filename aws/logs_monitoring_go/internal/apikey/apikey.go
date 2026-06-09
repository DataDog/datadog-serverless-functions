// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
)

const (
	apiKeyHeader      = "DD-API-KEY"
	validationTimeout = 3 * time.Second
)

var ErrInvalidAPIKey = errors.New("invalid Datadog API key")

func Validate(ctx context.Context, client *http.Client, url, key string) error {
	if !validFormat(key) {
		return errors.New("invalid Datadog API key format")
	}

	ctx, cancel := context.WithTimeout(ctx, validationTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("new request: %w", err)
	}

	req.Header.Set(apiKeyHeader, key)

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("client do: %w", err)
	}
	defer httpclient.DrainClose(resp)

	if resp.StatusCode == http.StatusForbidden {
		return ErrInvalidAPIKey
	}

	if resp.StatusCode != http.StatusOK {
		if body, err := io.ReadAll(resp.Body); err == nil {
			return fmt.Errorf("unexpected HTTP/%d response: %s", resp.StatusCode, body)
		}
		return fmt.Errorf("unexpected HTTP/%d response", resp.StatusCode)
	}

	return nil
}

func validFormat(key string) bool {
	return len(key) == 32
}
