// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
)

const (
	apiKeyValidationHeader = "DD-API-KEY"
	validationTimeout      = 5 * time.Second
)

type APIKeySource interface {
	Get(context.Context) (APIKey, error)
}

type APIKey string

func (k APIKey) String() string {
	return "[REDACTED API KEY]"
}

func (k APIKey) valid() bool {
	return len(k) == 32
}

// TODO: switch to https://docs.datadoghq.com/api/latest/key-management/validate-api-key once stable
func (k APIKey) Validate(ctx context.Context, client *http.Client, url string) error {
	if !k.valid() {
		return errors.New("wrong API key format")
	}

	ctx, cancel := context.WithTimeout(ctx, validationTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return fmt.Errorf("new request: %w", err)
	}
	req.Header.Set(apiKeyValidationHeader, string(k))

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("do request: %w", err)
	}
	defer httpclient.DrainClose(resp)

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("http %d", resp.StatusCode)
	}

	return nil
}
