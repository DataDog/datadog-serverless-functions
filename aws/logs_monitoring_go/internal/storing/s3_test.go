// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestS3_Store(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *sdkclient.MockS3)
		batch     Batch
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().
					PutObject(gomock.Any(), gomock.Any()).
					Return(nil, nil)
			},
			batch: Batch{
				Data:       testutil.GenerateJSONLogs(t, 100),
				StorageTag: "cloudwatch",
			},
		},
		"error on PutObject call": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().
					PutObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			batch: Batch{
				Data:       testutil.GenerateJSONLogs(t, 100),
				StorageTag: "cloudwatch",
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := sdkclient.NewMockS3(ctrl)
			tc.mockSetup(mock)
			storage := newS3(mock, "my-bucket")

			err := storage.Store(t.Context(), tc.batch)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestS3_Fetch(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *sdkclient.MockS3)
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *sdkclient.MockS3) {
				gomock.InOrder(
					m.EXPECT().
						ListObjectsV2(gomock.Any(), gomock.Any()).
						Return(&s3.ListObjectsV2Output{
							Contents: []s3types.Object{
								{Key: aws.String("failed_events/2026/06/01/120000000_req-id_1.json")},
								{Key: aws.String("failed_events/2026/06/01/120000000_req-id_2.json")},
							},
						}, nil),
					m.EXPECT().
						GetObject(gomock.Any(), gomock.Any()).
						Return(&s3.GetObjectOutput{
							Body:     io.NopCloser(bytes.NewReader(json.RawMessage(`[]`))),
							Metadata: map[string]string{},
						}, nil),
					m.EXPECT().
						GetObject(gomock.Any(), gomock.Any()).
						Return(&s3.GetObjectOutput{
							Body:     io.NopCloser(bytes.NewReader(json.RawMessage(`[]`))),
							Metadata: map[string]string{},
						}, nil),
				)
			},
		},
		"error on ListObjectsV2 call": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().
					ListObjectsV2(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			wantErr: true,
		},
		"error on GetObject call": {
			mockSetup: func(m *sdkclient.MockS3) {
				gomock.InOrder(
					m.EXPECT().
						ListObjectsV2(gomock.Any(), gomock.Any()).
						Return(&s3.ListObjectsV2Output{
							Contents: []s3types.Object{
								{Key: aws.String("failed_events/2026/06/01/120000000_req-id_1.json")},
							},
						}, nil),
					m.EXPECT().
						GetObject(gomock.Any(), gomock.Any()).
						Return(nil, errors.New("denied")),
				)
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := sdkclient.NewMockS3(ctrl)
			tc.mockSetup(mock)
			storage := newS3(mock, "failed_events")

			for _, err := range storage.Fetch(t.Context()) {
				if tc.wantErr {
					require.Error(t, err)
					return
				}
				require.NoError(t, err)
			}
		})
	}
}

func TestS3_Delete(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *sdkclient.MockS3)
		batch     Batch
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().
					DeleteObject(gomock.Any(), gomock.Any()).
					Return(nil, nil)
			},
			batch: Batch{
				DeleteKey: "failed_events/2026/06/01/120000000_req-id_1.json",
			},
		},
		"error on DeleteObject call": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().
					DeleteObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			batch: Batch{
				DeleteKey: "failed_events/2026/06/01/120000000_req-id_1.json",
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := sdkclient.NewMockS3(ctrl)
			tc.mockSetup(mock)
			storage := newS3(mock, "my-bucket")

			err := storage.Delete(t.Context(), tc.batch)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}
