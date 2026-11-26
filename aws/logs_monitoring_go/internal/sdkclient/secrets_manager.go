// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=secrets_manager.go -package=mocks -destination=mocks/secrets_manager.go

import (
	"context"
	"sync"

	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

var GetSecretsManager = sync.OnceValues(func() (SecretsManager, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return secretsmanager.NewFromConfig(cfg), nil
})

type SecretsManager interface {
	GetSecretValue(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error)
}
