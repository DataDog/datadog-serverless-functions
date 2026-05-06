// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"bytes"
	"errors"
	"io"
	"regexp"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/google/go-cmp/cmp"
	"go.uber.org/mock/gomock"
)

var (
	testS3EventRecord = events.S3EventRecord{
		S3: events.S3Entity{
			Bucket: events.S3Bucket{Name: "b"},
			Object: events.S3Object{URLDecodedKey: "k"},
		},
	}

	testCloudTrailKey         = "601427279990_CloudTrail_us-east-1_20210503T0000Z_QrttGEk4ZcBTLwj5.json.gz"
	testCloudTrailEventRecord = events.S3EventRecord{
		S3: events.S3Entity{
			Bucket: events.S3Bucket{Name: "trail-bucket"},
			Object: events.S3Object{URLDecodedKey: testCloudTrailKey},
		},
	}
)

func TestProcessS3Record(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup   func(m *MockS3APIClient)
		cfg         *config.Config
		eventRecord events.S3EventRecord
		want        []model.LogEntry
		wantErr     bool
	}{
		"single line": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("line1", "s3", "s3", nil)},
		},
		"multiple lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1\nline2\nline3")),
					}, nil)
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testS3EventRecord,
			want: []model.LogEntry{
				wantS3Entry("line1", "s3", "s3", nil),
				wantS3Entry("line2", "s3", "s3", nil),
				wantS3Entry("line3", "s3", "s3", nil),
			},
		},
		"empty file": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("")),
					}, nil)
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testS3EventRecord,
			want:        nil,
		},
		"s3 error": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("access denied"))
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testS3EventRecord,
			wantErr:     true,
		},
		"ddtags extraction": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader(`{"ddtags":"env:prod,service:myapp","msg":"hello"}`)),
					}, nil)
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry(`{"msg":"hello"}`, "s3", "myapp", model.Tags{"env:prod"})},
		},
		"invalid utf8 stripped": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("hello\x80world")),
					}, nil)
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("helloworld", "s3", "s3", nil)},
		},
		"multiline groups continuation lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n2024-01-15 INFO started")),
					}, nil)
			},
			cfg:         &config.Config{S3MultilineLogRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
			eventRecord: testS3EventRecord,
			want: []model.LogEntry{
				wantS3Entry("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n", "s3", "s3", nil),
				wantS3Entry("2024-01-15 INFO started", "s3", "s3", nil),
			},
		},
		"multiline flushes at eof": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR\n    stacktrace")),
					}, nil)
			},
			cfg:         &config.Config{S3MultilineLogRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("2024-01-15 ERROR\n    stacktrace", "s3", "s3", nil)},
		},
		"custom tags passed through": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			cfg:         &config.Config{Tags: model.Tags{"env:prod", "team:aws"}},
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("line1", "s3", "s3", model.Tags{"env:prod", "team:aws"})},
		},
		"cloudtrail with ec2 host": {
			mockSetup: func(m *MockS3APIClient) {
				data := testutil.MustGzipJSON(t, map[string]any{
					"Records": []any{
						map[string]any{
							"eventName": "DescribeTable",
							"userIdentity": map[string]any{
								"arn": "arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d",
							},
						},
					},
				})
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(bytes.NewReader(data)),
					}, nil)
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testCloudTrailEventRecord,
			want: []model.LogEntry{
				wantCloudTrailEntry(
					`{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}`,
					"i-08014e4f62ccf762d",
				),
			},
		},
		"cloudtrail without ec2 host": {
			mockSetup: func(m *MockS3APIClient) {
				data := testutil.MustGzipJSON(t, map[string]any{
					"Records": []any{
						map[string]any{
							"eventName": "DescribeTable",
							"userIdentity": map[string]any{
								"arn": "arn:aws:iam::601427279990:user/admin",
							},
						},
					},
				})
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(bytes.NewReader(data)),
					}, nil)
			},
			cfg:         testutil.EmptyConfig(),
			eventRecord: testCloudTrailEventRecord,
			want: []model.LogEntry{
				wantCloudTrailEntry(
					`{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:iam::601427279990:user/admin"}}`,
					"",
				),
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := NewMockS3APIClient(ctrl)
			tc.mockSetup(mock)

			out := make(chan model.LogEntry, len(tc.want))
			handler := NewS3(tc.cfg)

			err := handler.processRecord(t.Context(), mock, out, tc.eventRecord, testutil.LambdaOrigin())
			close(out)

			var got []model.LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			if tc.wantErr {
				if err == nil {
					t.Fatal("want error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func wantCloudTrailEntry(message, host string) model.LogEntry {
	entry := model.NewLogEntry()
	entry.Message = message
	entry.Host = host
	entry.Source = sourceCloudtrail
	entry.Service = sourceCloudtrail
	entry.Metadata = model.S3Metadata{
		LambdaOrigin: testutil.LambdaOrigin(),
		Origin:       model.S3Origin{Bucket: "trail-bucket", Key: testCloudTrailKey},
	}
	return entry
}

func wantS3Entry(message, source, service string, tags model.Tags) model.LogEntry {
	entry := model.NewLogEntry()
	entry.Message = message
	entry.Source = source
	entry.Service = service
	entry.Tags = tags
	entry.Metadata = model.S3Metadata{
		LambdaOrigin: testutil.LambdaOrigin(),
		Origin:       model.S3Origin{Bucket: "b", Key: "k"},
	}
	return entry
}
