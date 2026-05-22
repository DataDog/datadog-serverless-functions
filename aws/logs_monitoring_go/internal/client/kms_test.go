// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package client

import (
	"encoding/base64"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestDecryptKMSCiphertext(t *testing.T) {
	validCiphertext := base64.StdEncoding.EncodeToString([]byte("encrypted-blob"))

	tests := map[string]struct {
		mockSetup  func(m *MockKMS)
		ciphertext string
		wantKey    string
		wantErr    bool
	}{
		"success": {
			mockSetup: func(m *MockKMS) {
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
			mockSetup: func(m *MockKMS) {
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
			mockSetup:  func(m *MockKMS) {},
			ciphertext: "not-valid-base64!@#$",
			wantErr:    true,
		},
		"aws_error": {
			mockSetup: func(m *MockKMS) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("InvalidCiphertextException: invalid ciphertext"))
			},
			ciphertext: validCiphertext,
			wantErr:    true,
		},
		"nil_plaintext": {
			mockSetup: func(m *MockKMS) {
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
			mock := NewMockKMS(ctrl)
			tc.mockSetup(mock)

			got, err := DecryptKMSCiphertext(t.Context(), mock, tc.ciphertext)
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.wantKey, got)
		})
	}
}
