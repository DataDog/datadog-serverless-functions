// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/s3"
	"go.uber.org/mock/gomock"
)

func TestGetS3Object(t *testing.T) {
	tests := map[string]struct {
		mockSetup func(m *MockS3APIClient)
		bucket    string
		key       string
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().
					GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("content")),
					}, nil)
			},
			bucket: "my-bucket",
			key:    "my-key",
		},
		"error": {
			mockSetup: func(m *MockS3APIClient) {
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
			ctrl := gomock.NewController(t)
			mock := NewMockS3APIClient(ctrl)
			tc.mockSetup(mock)

			body, err := getS3Object(context.Background(), mock, tc.bucket, tc.key)

			if tc.wantErr {
				if err == nil {
					t.Fatal("want error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			defer body.Close()
		})
	}
}
