// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

import (
	"errors"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestSQS_Store(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *sdkclient.MockSQS)
		batch     Batch
		wantErr   bool
	}{
		"five 100KB logs send one message": {
			mockSetup: func(m *sdkclient.MockSQS) {
				m.EXPECT().
					SendMessage(gomock.Any(), gomock.Any()).
					Return(nil, nil)
			},
			batch: Batch{
				Data: testutil.GenerateJSONLogs(t, 100*1024, 100*1024, 100*1024, 100*1024, 100*1024),
			},
		},
		"two 512KB logs send two messages": {
			mockSetup: func(m *sdkclient.MockSQS) {
				m.EXPECT().
					SendMessage(gomock.Any(), gomock.Any()).
					Times(2).
					Return(nil, nil)
			},
			batch: Batch{
				Data: testutil.GenerateJSONLogs(t, 512*1024, 512*1024),
			},
		},
		"one 1MiB log send no message": {
			mockSetup: func(m *sdkclient.MockSQS) {
			},
			batch: Batch{
				Data: testutil.GenerateJSONLogs(t, 1*1024*1024),
			},
		},
		"error on SendMessage call": {
			mockSetup: func(m *sdkclient.MockSQS) {
				m.EXPECT().
					SendMessage(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			batch: Batch{
				Data: testutil.GenerateJSONLogs(t, 1024),
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := sdkclient.NewMockSQS(ctrl)
			tc.mockSetup(mock)
			sqs := newSQS(mock, "https://sqs.us-east-1.amazonaws.com/123456789012/MyQueue")

			err := sqs.Store(t.Context(), tc.batch)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestSQS_Fetch(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *sdkclient.MockSQS)
		wantErr   bool
	}{
		"exit on empty poll": {
			mockSetup: func(m *sdkclient.MockSQS) {
				gomock.InOrder(
					m.EXPECT().
						ReceiveMessage(gomock.Any(), gomock.Any()).
						Return(&sqs.ReceiveMessageOutput{
							Messages: []types.Message{{}},
						}, nil),
					m.EXPECT().
						ReceiveMessage(gomock.Any(), gomock.Any()).
						Return(&sqs.ReceiveMessageOutput{
							Messages: []types.Message{{}},
						}, nil),
					m.EXPECT().
						ReceiveMessage(gomock.Any(), gomock.Any()).
						Return(&sqs.ReceiveMessageOutput{}, nil),
				)
			},
		},
		"error on ReceiveMessage": {
			mockSetup: func(m *sdkclient.MockSQS) {
				m.EXPECT().
					ReceiveMessage(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := sdkclient.NewMockSQS(ctrl)
			tc.mockSetup(mock)
			s := newSQS(mock, "https://sqs.us-east-1.amazonaws.com/123456789012/MyQueue")

			for _, err := range s.Fetch(t.Context()) {
				if tc.wantErr {
					require.Error(t, err)
					return
				}
				require.NoError(t, err)
			}
		})
	}
}

func TestSQS_Delete(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *sdkclient.MockSQS)
		batch     Batch
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *sdkclient.MockSQS) {
				m.EXPECT().
					DeleteMessage(gomock.Any(), gomock.Any()).
					Return(nil, nil)
			},
			batch: Batch{
				DeleteKey: "MbZj6wDWli+JvwwJaBV+3d=",
			},
		},
		"error on DeleteMessage call": {
			mockSetup: func(m *sdkclient.MockSQS) {
				m.EXPECT().
					DeleteMessage(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			batch: Batch{
				DeleteKey: "MbZj6wDWli+JvwwJaBV+3d=",
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := sdkclient.NewMockSQS(ctrl)
			tc.mockSetup(mock)
			sqs := newSQS(mock, "https://sqs.us-east-1.amazonaws.com/123456789012/MyQueue")

			err := sqs.Delete(t.Context(), tc.batch)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}
