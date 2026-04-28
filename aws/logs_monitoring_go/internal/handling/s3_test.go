// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
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
	testS3Record = events.S3EventRecord{
		S3: events.S3Entity{
			Bucket: events.S3Bucket{Name: "b"},
			Object: events.S3Object{URLDecodedKey: "k"},
		},
	}
	testLambdaOrigin = model.LambdaOrigin{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"}
)

func wantS3Entry(message, source, service string, tags model.Tags) model.LogEntry {
	entry := model.NewLogEntry()
	entry.Message = message
	entry.Source = source
	entry.Service = service
	entry.Tags = tags
	entry.Metadata = model.S3Metadata{
		LambdaOrigin: testLambdaOrigin,
		Origin:       model.S3Origin{Bucket: "b", Key: "k"},
	}
	return entry
}

func TestProcessS3Record(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup func(m *MockS3APIClient)
		cfg       *config.Config
		chanSize  int
		want      []model.LogEntry
		wantErr   bool
	}{
		"single line": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			cfg:      testutil.EmptyConfig(),
			chanSize: 1,
			want:     []model.LogEntry{wantS3Entry("line1", "s3", "s3", model.Tags{"service:s3"})},
		},
		"multiple lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1\nline2\nline3")),
					}, nil)
			},
			cfg:      testutil.EmptyConfig(),
			chanSize: 3,
			want: []model.LogEntry{
				wantS3Entry("line1", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("line2", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("line3", "s3", "s3", model.Tags{"service:s3"}),
			},
		},
		"empty file": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("")),
					}, nil)
			},
			cfg:  testutil.EmptyConfig(),
			want: nil,
		},
		"s3 error": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("access denied"))
			},
			cfg:     testutil.EmptyConfig(),
			wantErr: true,
		},
		"ddtags extraction": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader(`{"ddtags":"env:prod,service:myapp","msg":"hello"}`)),
					}, nil)
			},
			cfg:      testutil.EmptyConfig(),
			chanSize: 1,
			want:     []model.LogEntry{wantS3Entry(`{"msg":"hello"}`, "s3", "myapp", model.Tags{"env:prod", "service:myapp"})},
		},
		"invalid utf8 stripped": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("hello\x80world")),
					}, nil)
			},
			cfg:      testutil.EmptyConfig(),
			chanSize: 1,
			want:     []model.LogEntry{wantS3Entry("helloworld", "s3", "s3", model.Tags{"service:s3"})},
		},
		"multiline groups continuation lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n2024-01-15 INFO started")),
					}, nil)
			},
			cfg:      &config.Config{S3MultilineLogRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
			chanSize: 2,
			want: []model.LogEntry{
				wantS3Entry("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("2024-01-15 INFO started", "s3", "s3", model.Tags{"service:s3"}),
			},
		},
		"multiline flushes at eof": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR\n    stacktrace")),
					}, nil)
			},
			cfg:      &config.Config{S3MultilineLogRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
			chanSize: 1,
			want:     []model.LogEntry{wantS3Entry("2024-01-15 ERROR\n    stacktrace", "s3", "s3", model.Tags{"service:s3"})},
		},
		"custom tags passed through": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			cfg:      &config.Config{Tags: model.Tags{"env:prod", "team:aws"}},
			chanSize: 1,
			want:     []model.LogEntry{wantS3Entry("line1", "s3", "s3", model.Tags{"service:s3", "env:prod", "team:aws"})},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := NewMockS3APIClient(ctrl)
			tc.mockSetup(mock)

			out := make(chan model.LogEntry, tc.chanSize)
			handler := NewS3(tc.cfg)

			err := handler.processRecord(t.Context(), mock, out, testS3Record, testLambdaOrigin)
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
