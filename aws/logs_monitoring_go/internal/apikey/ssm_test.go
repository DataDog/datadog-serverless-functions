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
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	"github.com/aws/aws-sdk-go-v2/service/ssm/types"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestSSMAPIKeySource_Get(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *mocks.MockSSM)
		name      string
		want      APIKey
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *mocks.MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&ssm.GetParameterOutput{
						Parameter: &types.Parameter{
							Value: aws.String("abcdef1234567890abcdef1234567890"),
						},
					}, nil)
			},
			name: "/my/parameter/path",
			want: "abcdef1234567890abcdef1234567890",
		},
		"whitespace trimmed": {
			mockSetup: func(m *mocks.MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(&ssm.GetParameterOutput{
						Parameter: &types.Parameter{
							Value: aws.String("  abcdef1234567890abcdef1234567890  "),
						},
					}, nil)
			},
			name: "/my/parameter/path",
			want: "abcdef1234567890abcdef1234567890",
		},
		"error": {
			mockSetup: func(m *mocks.MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any(), gomock.Any()).
					Return(nil, errors.New("ParameterNotFound: parameter not found"))
			},
			name:    "/my/parameter/path",
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := mocks.NewMockSSM(ctrl)
			tc.mockSetup(mock)

			source := SSMAPIKeySource{Client: mock, Name: tc.name}
			got, err := source.Get(t.Context())
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
		mock := mocks.NewMockSSM(ctrl)

		var got string
		mock.EXPECT().
			GetParameter(gomock.Any(), gomock.Any(), gomock.Any()).
			DoAndReturn(func(_ context.Context, _ *ssm.GetParameterInput, optFns ...func(*ssm.Options)) (*ssm.GetParameterOutput, error) {
				var opts ssm.Options
				for _, fn := range optFns {
					fn(&opts)
				}
				got = opts.Region

				return &ssm.GetParameterOutput{
					Parameter: &types.Parameter{Value: aws.String("abcdef1234567890abcdef1234567890")},
				}, nil
			})

		source := SSMAPIKeySource{Client: mock, Name: "arn:aws:ssm:eu-west-3:012345678901:parameter/datadog/api-key"}
		_, err := source.Get(t.Context())

		require.NoError(t, err)
		assert.Equal(t, "eu-west-3", got)
	})
}
