// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"encoding/base64"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/google/go-cmp/cmp"
	"go.uber.org/mock/gomock"
)

func TestResolveFromKMS(t *testing.T) {
	validCiphertext := base64.StdEncoding.EncodeToString([]byte("encrypted-blob"))

	tests := map[string]struct {
		mockSetup  func(m *MockKMSAPIClient)
		ciphertext string
		wantKey    string
		wantErr    bool
	}{
		"success": {
			mockSetup: func(m *MockKMSAPIClient) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(&kms.DecryptOutput{
						Plaintext: []byte("abcdef1234567890abcdef1234567890"),
					}, nil)
			},
			ciphertext: validCiphertext,
			wantKey:    "abcdef1234567890abcdef1234567890",
		},
		"whitespace_trimmed": {
			mockSetup: func(m *MockKMSAPIClient) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(&kms.DecryptOutput{
						Plaintext: []byte("  abcdef1234567890abcdef1234567890  "),
					}, nil)
			},
			ciphertext: validCiphertext,
			wantKey:    "abcdef1234567890abcdef1234567890",
		},
		"invalid_base64": {
			mockSetup:  func(m *MockKMSAPIClient) {},
			ciphertext: "not-valid-base64!@#$",
			wantErr:    true,
		},
		"aws_error": {
			mockSetup: func(m *MockKMSAPIClient) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("InvalidCiphertextException: invalid ciphertext"))
			},
			ciphertext: validCiphertext,
			wantErr:    true,
		},
		"nil_plaintext": {
			mockSetup: func(m *MockKMSAPIClient) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(&kms.DecryptOutput{
						Plaintext: nil,
					}, nil)
			},
			ciphertext: validCiphertext,
			wantErr:    true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			ctrl := gomock.NewController(t)
			mock := NewMockKMSAPIClient(ctrl)
			tc.mockSetup(mock)

			got, err := resolveFromKMS(context.Background(), mock, tc.ciphertext)
			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if diff := cmp.Diff(tc.wantKey, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}
