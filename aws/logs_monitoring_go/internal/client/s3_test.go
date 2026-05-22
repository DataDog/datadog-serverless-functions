// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package client

import (
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestGetS3Object(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *MockS3)
		bucket    string
		key       string
		wantErr   bool
	}{
		"returns body on success": {
			mockSetup: func(m *MockS3) {
				m.EXPECT().
					GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("content")),
					}, nil)
			},
			bucket: "my-bucket",
			key:    "my-key",
		},
		"returns error on S3 failure": {
			mockSetup: func(m *MockS3) {
				m.EXPECT().
					GetObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New(""))
			},
			bucket:  "my-bucket",
			key:     "my-key",
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			ctrl := gomock.NewController(t)
			mock := NewMockS3(ctrl)
			tc.mockSetup(mock)

			body, err := GetS3Object(t.Context(), mock, tc.bucket, tc.key)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			_ = body.Close()
		})
	}
}
