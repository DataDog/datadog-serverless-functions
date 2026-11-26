// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"encoding/base64"
	"errors"
	"testing"
	"unicode/utf8"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient/mocks"
	"github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestKMSAPIKeySource_Get(t *testing.T) {
	t.Parallel()

	validCiphertext := base64.StdEncoding.EncodeToString([]byte("encrypted-blob"))

	tests := map[string]struct {
		mockSetup  func(m *mocks.MockKMS)
		ciphertext string
		want       APIKey
		wantErr    bool
	}{
		"success": {
			mockSetup: func(m *mocks.MockKMS) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(&kms.DecryptOutput{
						Plaintext: []byte("abcdef1234567890abcdef1234567890"),
					}, nil)
			},
			ciphertext: validCiphertext,
			want:       "abcdef1234567890abcdef1234567890",
		},
		"whitespace trimmed": {
			mockSetup: func(m *mocks.MockKMS) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(&kms.DecryptOutput{
						Plaintext: []byte("  abcdef1234567890abcdef1234567890  "),
					}, nil)
			},
			ciphertext: validCiphertext,
			want:       "abcdef1234567890abcdef1234567890",
		},
		"invalid base64": {
			mockSetup:  func(m *mocks.MockKMS) {},
			ciphertext: "not-valid-base64!@#$",
			wantErr:    true,
		},
		"error": {
			mockSetup: func(m *mocks.MockKMS) {
				m.EXPECT().
					Decrypt(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("InvalidCiphertextException: invalid ciphertext"))
			},
			ciphertext: validCiphertext,
			wantErr:    true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := mocks.NewMockKMS(ctrl)
			tc.mockSetup(mock)

			source := KMSAPIKeySource{Client: mock, Ciphertext: tc.ciphertext}
			got, err := source.Get(t.Context())
			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
		})
	}

	t.Run("non-UTF8 plaintext is base64 encoded", func(t *testing.T) {
		t.Parallel()

		plaintext := []byte{0xff, 0xfe, 0x00, 0x01}

		ctrl := gomock.NewController(t)
		mock := mocks.NewMockKMS(ctrl)
		mock.EXPECT().
			Decrypt(gomock.Any(), gomock.Any()).
			Return(&kms.DecryptOutput{Plaintext: plaintext}, nil)

		source := KMSAPIKeySource{Client: mock, Ciphertext: base64.StdEncoding.EncodeToString([]byte("cipher"))}
		got, err := source.Get(t.Context())

		require.NoError(t, err)
		assert.Equal(t, base64.StdEncoding.EncodeToString(plaintext), string(got))
		assert.True(t, utf8.ValidString(string(got)))
	})
}
