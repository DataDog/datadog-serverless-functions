// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"errors"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient/mocks"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestSecretsManagerAPIKeySource_Get(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *mocks.MockSecretsManager)
		arn       string
		want      APIKey
		wantErr   bool
	}{
		"plain": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("abcdef1234567890abcdef1234567890"),
					}, nil)
			},
			arn:  "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			want: "abcdef1234567890abcdef1234567890",
		},
		"DD_API_KEY json parsing": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String(`{"DD_API_KEY":"abcdef1234567890abcdef1234567890"}`),
					}, nil)
			},
			arn:  "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			want: "abcdef1234567890abcdef1234567890",
		},
		"apiKey json parsing": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String(`{"apikey":"abcdef1234567890abcdef1234567890"}`),
					}, nil)
			},
			arn:  "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			want: "abcdef1234567890abcdef1234567890",
		},
		"whitespace": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("  abcdef1234567890abcdef1234567890  \n"),
					}, nil)
			},
			arn:  "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			want: "abcdef1234567890abcdef1234567890",
		},
		"error": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(nil, errors.New("AccessDeniedException: access denied"))
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := mocks.NewMockSecretsManager(ctrl)
			tc.mockSetup(mock)

			secretsManager := SecretsManagerAPIKeySource{Client: mock, ARN: tc.arn}
			got, err := secretsManager.Get(t.Context())
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
		})
	}

	t.Run("cross region", func(t *testing.T) {
		t.Parallel()

		ctrl := gomock.NewController(t)
		mock := mocks.NewMockSecretsManager(ctrl)

		var got string
		mock.EXPECT().
			GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
			DoAndReturn(func(_ context.Context, _ *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error) {
				var opts secretsmanager.Options
				for _, fn := range optFns {
					fn(&opts)
				}
				got = opts.Region

				return &secretsmanager.GetSecretValueOutput{SecretString: aws.String("abcdef1234567890abcdef1234567890")}, nil
			})

		secretsManager := SecretsManagerAPIKeySource{Client: mock, ARN: "arn:aws:secretsmanager:eu-west-1:012345678901:secret:dd"}
		_, err := secretsManager.Get(t.Context())

		require.NoError(t, err)
		assert.Equal(t, "eu-west-1", got)
	})
}
