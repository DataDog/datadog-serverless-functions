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
	"go.uber.org/mock/gomock"
)

func TestResolveFromSecretsManager(t *testing.T) {
	tests := map[string]struct {
		mockSetup func(m *MockSecretsManagerAPIClient)
		arn       string
		wantKey   string
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *MockSecretsManagerAPIClient) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("abcdef1234567890abcdef1234567890"),
					}, nil)
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantKey: "abcdef1234567890abcdef1234567890",
		},
		"whitespace_trimmed": {
			mockSetup: func(m *MockSecretsManagerAPIClient) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("  abcdef1234567890abcdef1234567890  \n"),
					}, nil)
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantKey: "abcdef1234567890abcdef1234567890",
		},
		"aws_error": {
			mockSetup: func(m *MockSecretsManagerAPIClient) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("AccessDeniedException: access denied"))
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantErr: true,
		},
		"nil_secret_string": {
			mockSetup: func(m *MockSecretsManagerAPIClient) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: nil,
					}, nil)
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			ctrl := gomock.NewController(t)
			mock := NewMockSecretsManagerAPIClient(ctrl)
			tc.mockSetup(mock)

			got, err := resolveFromSecretsManager(context.Background(), mock, tc.arn)
			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tc.wantKey {
				t.Errorf("got %q, want %q", got, tc.wantKey)
			}
		})
	}
}
