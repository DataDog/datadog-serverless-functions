// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package client

import (
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
	"github.com/aws/aws-sdk-go-v2/service/ssm/types"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestFetchSSMParameter(t *testing.T) {
	tests := map[string]struct {
		mockSetup func(m *MockSSM)
		name      string
		wantKey   string
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any()).
					Return(&ssm.GetParameterOutput{
						Parameter: &types.Parameter{
							Value: aws.String("abcdef1234567890abcdef1234567890"),
						},
					}, nil)
			},
			name:    "/my/parameter/path",
			wantKey: "abcdef1234567890abcdef1234567890",
		},
		"whitespace_trimmed": {
			mockSetup: func(m *MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any()).
					Return(&ssm.GetParameterOutput{
						Parameter: &types.Parameter{
							Value: aws.String("  abcdef1234567890abcdef1234567890  "),
						},
					}, nil)
			},
			name:    "/my/parameter/path",
			wantKey: "abcdef1234567890abcdef1234567890",
		},
		"aws_error": {
			mockSetup: func(m *MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("ParameterNotFound: parameter not found"))
			},
			name:    "/my/parameter/path",
			wantErr: true,
		},
		"nil_parameter": {
			mockSetup: func(m *MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any()).
					Return(&ssm.GetParameterOutput{
						Parameter: nil,
					}, nil)
			},
			name:    "/my/parameter/path",
			wantErr: true,
		},
		"nil_value": {
			mockSetup: func(m *MockSSM) {
				m.EXPECT().
					GetParameter(gomock.Any(), gomock.Any()).
					Return(&ssm.GetParameterOutput{
						Parameter: &types.Parameter{
							Value: nil,
						},
					}, nil)
			},
			name:    "/my/parameter/path",
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			ctrl := gomock.NewController(t)
			mock := NewMockSSM(ctrl)
			tc.mockSetup(mock)

			got, err := FetchSSMParameter(t.Context(), mock, tc.name)
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.wantKey, got)
		})
	}
}
