// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

// const (
// 	testBucket = "my-bucket"
// 	testKey    = "failed_events/2026/06/01/120000000_req-id_1.json"
// )

// func TestS3_Put(t *testing.T) {
// 	t.Parallel()

// 	tests := map[string]struct {
// 		mockSetup  func(m *sdkclient.MockS3)
// 		storageTag string
// 		wantErr    bool
// 	}{
// 		"success": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					PutObject(gomock.Any(), gomock.Cond(func(input *s3.PutObjectInput) bool {
// 						return aws.ToString(input.Bucket) == testBucket &&
// 							strings.HasPrefix(aws.ToString(input.Key), prefix) &&
// 							input.Metadata["dd-storage-tag"] == "s3"
// 					})).
// 					Return(nil, nil)
// 			},
// 			storageTag: "s3",
// 		},
// 		"error": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					PutObject(gomock.Any(), gomock.Any()).
// 					Return(nil, errors.New(""))
// 			},
// 			wantErr: true,
// 		},
// 	}

// 	for name, tc := range tests {
// 		t.Run(name, func(t *testing.T) {
// 			t.Parallel()

// 			ctrl := gomock.NewController(t)
// 			mock := sdkclient.NewMockS3(ctrl)
// 			tc.mockSetup(mock)
// 			storage := newS3(mock, testBucket)

// 			err := storage.Put(t.Context(), []byte{}, tc.storageTag)

// 			if tc.wantErr {
// 				require.Error(t, err)
// 				return
// 			}
// 			require.NoError(t, err)
// 		})
// 	}
// }

// func TestS3_List(t *testing.T) {
// 	t.Parallel()

// 	tests := map[string]struct {
// 		mockSetup func(m *sdkclient.MockS3)
// 		wantKeys  []string
// 		wantErr   bool
// 	}{
// 		"success": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					ListObjectsV2(gomock.Any(), gomock.Cond(func(input *s3.ListObjectsV2Input) bool {
// 						return aws.ToString(input.Bucket) == testBucket &&
// 							aws.ToString(input.Prefix) == prefix
// 					})).
// 					Return(&s3.ListObjectsV2Output{
// 						Contents: []types.Object{
// 							{Key: aws.String("failed_events/2026/06/01/120000000_req-id_1.json")},
// 							{Key: aws.String("failed_events/2026/06/01/120000000_req-id_2.json")},
// 							{Key: aws.String("failed_events/2026/06/01/120000001_req-id_3.json")},
// 						},
// 					}, nil)
// 			},
// 			wantKeys: []string{
// 				"failed_events/2026/06/01/120000000_req-id_1.json",
// 				"failed_events/2026/06/01/120000000_req-id_2.json",
// 				"failed_events/2026/06/01/120000001_req-id_3.json",
// 			},
// 		},
// 		"error": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					ListObjectsV2(gomock.Any(), gomock.Any()).
// 					Return(nil, errors.New(""))
// 			},
// 			wantErr: true,
// 		},
// 	}

// 	for name, tc := range tests {
// 		t.Run(name, func(t *testing.T) {
// 			t.Parallel()

// 			ctrl := gomock.NewController(t)
// 			mock := sdkclient.NewMockS3(ctrl)
// 			tc.mockSetup(mock)
// 			storage := newS3(mock, testBucket)

// 			keys, err := storage.List(t.Context())

// 			if tc.wantErr {
// 				require.Error(t, err)
// 				return
// 			}
// 			require.NoError(t, err)
// 			assert.Equal(t, tc.wantKeys, keys)
// 		})
// 	}
// }

// func TestS3_Get(t *testing.T) {
// 	t.Parallel()

// 	tests := map[string]struct {
// 		mockSetup      func(m *sdkclient.MockS3)
// 		wantBody       []byte
// 		wantStorageTag string
// 		wantErr        bool
// 	}{
// 		"success": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					GetObject(gomock.Any(), gomock.Cond(func(input *s3.GetObjectInput) bool {
// 						return aws.ToString(input.Bucket) == testBucket &&
// 							aws.ToString(input.Key) == testKey
// 					})).
// 					Return(&s3.GetObjectOutput{
// 						Body:     io.NopCloser(strings.NewReader(`[{"message":"hello"}]`)),
// 						Metadata: map[string]string{"dd-storage-tag": "cloudwatch"},
// 					}, nil)
// 			},
// 			wantBody:       []byte(`[{"message":"hello"}]`),
// 			wantStorageTag: "cloudwatch",
// 		},
// 		"error": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					GetObject(gomock.Any(), gomock.Any()).
// 					Return(nil, errors.New(""))
// 			},
// 			wantErr: true,
// 		},
// 	}

// 	for name, tc := range tests {
// 		t.Run(name, func(t *testing.T) {
// 			t.Parallel()

// 			ctrl := gomock.NewController(t)
// 			mock := sdkclient.NewMockS3(ctrl)
// 			tc.mockSetup(mock)
// 			storage := newS3(mock, testBucket)

// 			body, storageTag, err := storage.Get(t.Context(), testKey)

// 			if tc.wantErr {
// 				require.Error(t, err)
// 				return
// 			}
// 			require.NoError(t, err)
// 			assert.Equal(t, tc.wantBody, body)
// 			assert.Equal(t, tc.wantStorageTag, storageTag)
// 		})
// 	}
// }

// func TestS3_Delete(t *testing.T) {
// 	t.Parallel()

// 	tests := map[string]struct {
// 		mockSetup func(m *sdkclient.MockS3)
// 		wantErr   bool
// 	}{
// 		"success": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					DeleteObject(gomock.Any(), gomock.Cond(func(input *s3.DeleteObjectInput) bool {
// 						return aws.ToString(input.Bucket) == testBucket &&
// 							aws.ToString(input.Key) == testKey
// 					})).
// 					Return(nil, nil)
// 			},
// 		},
// 		"error": {
// 			mockSetup: func(m *sdkclient.MockS3) {
// 				m.EXPECT().
// 					DeleteObject(gomock.Any(), gomock.Any()).
// 					Return(nil, errors.New(""))
// 			},
// 			wantErr: true,
// 		},
// 	}

// 	for name, tc := range tests {
// 		t.Run(name, func(t *testing.T) {
// 			t.Parallel()

// 			ctrl := gomock.NewController(t)
// 			mock := sdkclient.NewMockS3(ctrl)
// 			tc.mockSetup(mock)
// 			storage := newS3(mock, testBucket)

// 			err := storage.Delete(t.Context(), testKey)

// 			if tc.wantErr {
// 				require.Error(t, err)
// 				return
// 			}
// 			require.NoError(t, err)
// 		})
// 	}
// }
