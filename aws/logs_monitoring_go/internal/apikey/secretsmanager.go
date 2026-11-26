// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/aws/arn"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

type secretsManagerJSONFields struct {
	DdApiKey string `json:"DD_API_KEY"`
	ApiKey   string `json:"apiKey"`
}

type SecretsManagerAPIKeySource struct {
	Client sdkclient.SecretsManager
	ARN    string
}

func (ks *SecretsManagerAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	out, err := ks.Client.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(ks.ARN),
	}, func(o *secretsmanager.Options) {
		if parsed, err := arn.Parse(ks.ARN); err == nil && parsed.Region != "" {
			o.Region = parsed.Region
		}
	})
	if err != nil {
		return "", fmt.Errorf("get secret value %q: %w", ks.ARN, err)
	}

	if out.SecretString == nil {
		return "", fmt.Errorf("no value for secret %q", ks.ARN)
	}

	if !json.Valid([]byte(*out.SecretString)) {
		return APIKey(strings.TrimSpace(*out.SecretString)), nil
	}

	var parsed secretsManagerJSONFields
	if err := json.Unmarshal([]byte(*out.SecretString), &parsed); err != nil {
		return APIKey(strings.TrimSpace(*out.SecretString)), nil
	}

	parsed.DdApiKey = strings.TrimSpace(parsed.DdApiKey)
	if parsed.DdApiKey != "" {
		return APIKey(parsed.DdApiKey), nil
	}

	parsed.ApiKey = strings.TrimSpace(parsed.ApiKey)
	if parsed.ApiKey != "" {
		return APIKey(parsed.ApiKey), nil
	}

	return "", fmt.Errorf("no json value for secret %q", ks.ARN)
}
