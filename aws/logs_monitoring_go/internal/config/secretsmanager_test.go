// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
)

func GetSecretValueFromSecretsManager(ctx context.Context, api SecretsManagerGetSecretValueAPI, secretId string) (string, error) {
	secret, err := api.GetSecretValue(ctx, &secretsmanager.GetSecretValueInput{
		SecretId: &secretId,
	})
	if err != nil {
		return "", err
	}
	if secret == nil {
		return "", errors.New("got nil secret")
	}
	if secret.SecretString == nil {
		return "", errors.New("secret has no string value")
	}
	return *secret.SecretString, nil
}

type mockGetSecretValueAPI func(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error)

func (m mockGetSecretValueAPI) GetSecretValue(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error) {
	return m(ctx, params, optFns...)
}

func TestGetSecretFromSecretsManager(t *testing.T) {
	tests := map[string]struct {
		client   func(t *testing.T) SecretsManagerGetSecretValueAPI
		secretId string
		expect   string
		wantErr  bool
	}{
		"default": {
			client: func(t *testing.T) SecretsManagerGetSecretValueAPI {
				return mockGetSecretValueAPI(func(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error) {
					t.Helper()
					if params.SecretId == nil {
						t.Fatal("expect SecretId not to be nil")
					}
					return &secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("my-32-characters-datadog-api-key"),
					}, nil
				})
			},
			secretId: "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret-abcdef",
			expect:   "my-32-characters-datadog-api-key",
		},
		"nil_secret_string": {
			client: func(t *testing.T) SecretsManagerGetSecretValueAPI {
				return mockGetSecretValueAPI(func(ctx context.Context, params *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error) {
					t.Helper()
					if params.SecretId == nil {
						t.Fatal("expect SecretId not to be nil")
					}
					return &secretsmanager.GetSecretValueOutput{
						SecretString: nil,
					}, nil
				})
			},
			secretId: "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret-abcdef",
			wantErr:  true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			secretId, err := GetSecretValueFromSecretsManager(context.Background(), tc.client(t), tc.secretId)
			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Errorf("expect no error, got %v", err)
			}
			if secretId != tc.expect {
				t.Errorf("expect %v, got %v", tc.expect, secretId)
			}
		})
	}
}
