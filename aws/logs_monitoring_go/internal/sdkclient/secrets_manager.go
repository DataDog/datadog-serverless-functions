// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=secrets_manager.go -package=sdkclient -destination=secrets_manager_mockgen.go

import (
	"context"
	"fmt"
	"strings"
	"sync"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

var getSecretsManager = sync.OnceValues(func() (SecretsManager, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return secretsmanager.NewFromConfig(cfg), nil
})

type SecretsManager interface {
	GetSecretValue(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error)
}

func ResolveFromSecretsManager(ctx context.Context, arn string) (string, error) {
	smClient, err := getSecretsManager()
	if err != nil {
		return "", err
	}
	return FetchSecret(ctx, smClient, arn)
}

func FetchSecret(ctx context.Context, smClient SecretsManager, arn string) (string, error) {
	result, err := smClient.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: aws.String(arn),
	})
	if err != nil {
		return "", fmt.Errorf("fetching secret %q: %w", arn, err)
	}

	if result.SecretString == nil {
		return "", fmt.Errorf("secret %q has no string value", arn)
	}

	return strings.TrimSpace(*result.SecretString), nil
}
