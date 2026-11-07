// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storage

import (
	"bytes"
	"context"
	"encoding/json/jsontext"
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient/mocks"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/aws/aws-lambda-go/lambdacontext"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	s3types "github.com/aws/aws-sdk-go-v2/service/s3/types"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

const testFunctionARN = "arn:aws:lambda:us-east-1:123456789012:function:my-function"

func contextWithLambda(arn string) context.Context {
	return lambdacontext.NewContext(context.Background(), &lambdacontext.LambdaContext{InvokedFunctionArn: arn})
}

func TestS3_Store(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *mocks.MockS3)
		batch     Batch
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *mocks.MockS3) {
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
			mockSetup: func(m *mocks.MockS3) {
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
			mock := mocks.NewMockS3(ctrl)
			tc.mockSetup(mock)
			storage := NewS3(mock, "my-bucket", "my-function")

			err := storage.Store(contextWithLambda(testFunctionARN), tc.batch)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}

func TestS3_Store_KeyPrefix(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		ctx        context.Context
		wantPrefix string
	}{
		"with lambda context": {
			ctx:        contextWithLambda(testFunctionARN),
			wantPrefix: "failed_events/123456789012/us-east-1/my-function/",
		},
		"without lambda context": {
			ctx:        t.Context(),
			wantPrefix: "failed_events/unknown/unknown/my-function/",
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := mocks.NewMockS3(ctrl)

			var gotKey string
			mock.EXPECT().
				PutObject(gomock.Any(), gomock.Any()).
				DoAndReturn(func(_ context.Context, in *s3.PutObjectInput, _ ...any) (*s3.PutObjectOutput, error) {
					gotKey = aws.ToString(in.Key)
					return nil, nil
				})
			storage := NewS3(mock, "my-bucket", "my-function")

			err := storage.Store(tc.ctx, Batch{Data: testutil.GenerateJSONLogs(t, 100), StorageTag: "cloudwatch"})

			require.NoError(t, err)
			require.True(t, strings.HasPrefix(gotKey, tc.wantPrefix), "key %q does not have prefix %q", gotKey, tc.wantPrefix)
		})
	}
}

func TestS3_Fetch(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *mocks.MockS3)
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *mocks.MockS3) {
				gomock.InOrder(
					m.EXPECT().
						ListObjectsV2(gomock.Any(), gomock.Any()).
						Return(&s3.ListObjectsV2Output{
							Contents: []s3types.Object{
								{Key: aws.String("failed_events/123456789012/us-east-1/my-function/2026/06/01/120000_req-id_4b1f6c2a-6f2e-4e3a-9c3e-1a2b3c4d5e6f.json")},
								{Key: aws.String("failed_events/123456789012/us-east-1/my-function/2026/06/01/120000_req-id_9f0e8d7c-5b4a-4c3d-8e2f-1a2b3c4d5e6f.json")},
							},
						}, nil),
					m.EXPECT().
						GetObject(gomock.Any(), gomock.Any()).
						Return(&s3.GetObjectOutput{
							Body:     io.NopCloser(bytes.NewReader(jsontext.Value(`[]`))),
							Metadata: map[string]string{},
						}, nil),
					m.EXPECT().
						GetObject(gomock.Any(), gomock.Any()).
						Return(&s3.GetObjectOutput{
							Body:     io.NopCloser(bytes.NewReader(jsontext.Value(`[]`))),
							Metadata: map[string]string{},
						}, nil),
				)
			},
		},
		"error on ListObjectsV2 call": {
			mockSetup: func(m *mocks.MockS3) {
				m.EXPECT().
					ListObjectsV2(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			wantErr: true,
		},
		"error on GetObject call": {
			mockSetup: func(m *mocks.MockS3) {
				gomock.InOrder(
					m.EXPECT().
						ListObjectsV2(gomock.Any(), gomock.Any()).
						Return(&s3.ListObjectsV2Output{
							Contents: []s3types.Object{
								{Key: aws.String("failed_events/123456789012/us-east-1/my-function/2026/06/01/120000_req-id_4b1f6c2a-6f2e-4e3a-9c3e-1a2b3c4d5e6f.json")},
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
			mock := mocks.NewMockS3(ctrl)
			tc.mockSetup(mock)
			storage := NewS3(mock, "failed_events", "my-function")

			for _, err := range storage.Fetch(contextWithLambda(testFunctionARN)) {
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
		mockSetup func(m *mocks.MockS3)
		batch     Batch
		wantErr   bool
	}{
		"success": {
			mockSetup: func(m *mocks.MockS3) {
				m.EXPECT().
					DeleteObject(gomock.Any(), gomock.Any()).
					Return(nil, nil)
			},
			batch: Batch{
				DeleteKey: "failed_events/123456789012/us-east-1/my-function/2026/06/01/120000_req-id_4b1f6c2a-6f2e-4e3a-9c3e-1a2b3c4d5e6f.json",
			},
		},
		"error on DeleteObject call": {
			mockSetup: func(m *mocks.MockS3) {
				m.EXPECT().
					DeleteObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("denied"))
			},
			batch: Batch{
				DeleteKey: "failed_events/123456789012/us-east-1/my-function/2026/06/01/120000_req-id_4b1f6c2a-6f2e-4e3a-9c3e-1a2b3c4d5e6f.json",
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := mocks.NewMockS3(ctrl)
			tc.mockSetup(mock)
			storage := NewS3(mock, "my-bucket", "my-function")

			err := storage.Delete(t.Context(), tc.batch)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}
