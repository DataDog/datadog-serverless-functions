// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

import (
	"context"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/secretsmanager"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient/mocks"
)

func TestFetchSecret(t *testing.T) {
	tests := map[string]struct {
		mockSetup func(m *mocks.MockSecretsManager)
		arn       string
		wantKey   string
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("abcdef1234567890abcdef1234567890"),
					}, nil)
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantKey: "abcdef1234567890abcdef1234567890",
		},
		"whitespace_trimmed": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("  abcdef1234567890abcdef1234567890  \n"),
					}, nil)
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantKey: "abcdef1234567890abcdef1234567890",
		},
		"aws_error": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(nil, errors.New("AccessDeniedException: access denied"))
			},
			arn:     "arn:aws:secretsmanager:us-east-1:012345678901:secret:my-secret",
			wantErr: true,
		},
		"nil_secret_string": {
			mockSetup: func(m *mocks.MockSecretsManager) {
				m.EXPECT().
					GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
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
			mock := mocks.NewMockSecretsManager(ctrl)
			tc.mockSetup(mock)

			got, err := FetchSecret(t.Context(), mock, tc.arn)
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.wantKey, got)
		})
	}
}

func TestFetchSecretUsesRegionFromARN(t *testing.T) {
	tests := map[string]struct {
		arn  string
		want string
	}{
		"cross region arn": {
			arn:  "arn:aws:secretsmanager:eu-west-3:012345678901:secret:dd",
			want: "eu-west-3",
		},
		"non arn keeps default resolution": {
			arn: "dd-api-key",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			ctrl := gomock.NewController(t)
			mock := mocks.NewMockSecretsManager(ctrl)

			var gotRegion string
			mock.EXPECT().
				GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
				DoAndReturn(func(_ context.Context, _ *secretsmanager.GetSecretValueInput, optFns ...func(*secretsmanager.Options)) (*secretsmanager.GetSecretValueOutput, error) {
					var opts secretsmanager.Options
					for _, fn := range optFns {
						fn(&opts)
					}
					gotRegion = opts.Region

					return &secretsmanager.GetSecretValueOutput{
						SecretString: aws.String("abcdef1234567890abcdef1234567890"),
					}, nil
				})

			_, err := FetchSecret(t.Context(), mock, tc.arn)

			require.NoError(t, err)
			assert.Equal(t, tc.want, gotRegion)
		})
	}
}

func TestFetchSecretParsesJSONSecret(t *testing.T) {
	ctrl := gomock.NewController(t)
	mock := mocks.NewMockSecretsManager(ctrl)
	mock.EXPECT().
		GetSecretValue(gomock.Any(), gomock.Any(), gomock.Any()).
		Return(&secretsmanager.GetSecretValueOutput{
			SecretString: aws.String(`{"apiKey":"abcdef1234567890abcdef1234567890"}`),
		}, nil)

	got, err := FetchSecret(t.Context(), mock, "arn:aws:secretsmanager:us-east-1:012345678901:secret:dd")

	require.NoError(t, err)
	assert.Equal(t, "abcdef1234567890abcdef1234567890", got)
}

func TestAPIKeyFromSecret(t *testing.T) {
	t.Parallel()

	const (
		arn = "arn:aws:secretsmanager:us-east-1:012345678901:secret:dd"
		key = "abcdef1234567890abcdef1234567890"
	)

	tests := map[string]struct {
		secret  string
		want    string
		wantErr string
	}{
		"plain string":              {secret: key, want: key},
		"plain string with symbols": {secret: "not-json-{at-all", want: "not-json-{at-all"},
		"json dd_api_key":           {secret: `{"DD_API_KEY":"` + key + `"}`, want: key},
		"json apikey":               {secret: `{"apiKey":"` + key + `"}`, want: key},
		"dd_api_key wins": {
			secret: `{"apiKey":"wrong-key-wrong-key-wrong-key-00","DD_API_KEY":"` + key + `"}`,
			want:   key,
		},
		"json extra fields ignored": {
			secret: `{"apiKey":"` + key + `","appKey":"other","rotation":7}`,
			want:   key,
		},
		"json value trimmed": {secret: `{"apiKey":"  ` + key + `  "}`, want: key},
		"json without known field": {
			secret:  `{"username":"dd","password":"secret"}`,
			wantErr: `has no DD_API_KEY or apiKey field`,
		},
		"json empty object": {secret: `{}`, wantErr: "has no DD_API_KEY or apiKey field"},
		"json null":         {secret: `null`, wantErr: "has no DD_API_KEY or apiKey field"},
		"json non string value": {
			secret:  `{"apiKey":12345}`,
			wantErr: `field "apiKey" is not a string`,
		},
		"json array is not an object":  {secret: `["a","b"]`, want: `["a","b"]`},
		"json number is not an object": {secret: `1234`, want: "1234"},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got, err := apiKeyFromSecret(arn, tc.secret)

			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
				assert.Empty(t, got)
				return
			}

			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
		})
	}
}
