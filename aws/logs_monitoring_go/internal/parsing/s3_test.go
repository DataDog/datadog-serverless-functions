// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"context"
	"errors"
	"io"
	"regexp"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/google/go-cmp/cmp"
	"go.uber.org/mock/gomock"
)

func TestProcessS3Record(t *testing.T) {
	tests := map[string]struct {
		mockSetup func(m *MockS3APIClient)
		chanSize  int
		rc        s3RecordContext
		want      []model.S3LogEntry
		wantErr   bool
	}{
		"single_line": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			chanSize: 1,
			rc:       s3RecordContext{tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k"},
			want: []model.S3LogEntry{{
				Message:        "line1",
				Source:         "s3",
				SourceCategory: "aws",
				Service:        "s3",
				Tags:           model.Tags{"service:s3"},
				Metadata: model.S3Metadata{
					S3Context: model.S3Context{Bucket: "b", Key: "k"},
				},
			}},
		},
		"multiple_lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1\nline2\nline3")),
					}, nil)
			},
			chanSize: 3,
			rc:       s3RecordContext{tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k"},
			want: []model.S3LogEntry{
				{Message: "line1", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
				{Message: "line2", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
				{Message: "line3", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
			},
		},
		"empty_file": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("")),
					}, nil)
			},
			chanSize: 0,
			rc:       s3RecordContext{tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k"},
			want:     nil,
		},
		"s3_error": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("access denied"))
			},
			chanSize: 1,
			rc:       s3RecordContext{bucket: "b", key: "k"},
			wantErr:  true,
		},
		"ddtags_extraction": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader(`{"ddtags":"env:prod,service:myapp","msg":"hello"}`)),
					}, nil)
			},
			chanSize: 1,
			rc:       s3RecordContext{tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k"},
			want: []model.S3LogEntry{{
				Message:        `{"msg":"hello"}`,
				Source:         "s3",
				SourceCategory: "aws",
				Service:        "myapp",
				Tags:           model.Tags{"env:prod", "service:myapp"},
				Metadata:       model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}},
			}},
		},
		"invalid_utf8_stripped": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("hello\x80world")),
					}, nil)
			},
			chanSize: 1,
			rc:       s3RecordContext{tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k"},
			want: []model.S3LogEntry{{
				Message:        "helloworld",
				Source:         "s3",
				SourceCategory: "aws",
				Service:        "s3",
				Tags:           model.Tags{"service:s3"},
				Metadata:       model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}},
			}},
		},
		"multiline_groups_continuation_lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n2024-01-15 INFO started")),
					}, nil)
			},
			chanSize: 2,
			rc: s3RecordContext{
				tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k",
				multilineRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`),
			},
			want: []model.S3LogEntry{
				{Message: "2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
				{Message: "2024-01-15 INFO started", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
			},
		},
		"multiline_flushes_at_eof": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR\n    stacktrace")),
					}, nil)
			},
			chanSize: 1,
			rc: s3RecordContext{
				tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k",
				multilineRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`),
			},
			want: []model.S3LogEntry{{
				Message:        "2024-01-15 ERROR\n    stacktrace",
				Source:         "s3",
				SourceCategory: "aws",
				Service:        "s3",
				Tags:           model.Tags{"service:s3"},
				Metadata:       model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}},
			}},
		},
		"multimatch_single_line": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR2024-01-15 ERROR2024-01-15 ERROR\n    stacktrace")),
					}, nil)
			},
			chanSize: 3,
			rc: s3RecordContext{
				tags: model.Tags{}, source: "s3", service: "s3", bucket: "b", key: "k",
				multilineRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`),
			},
			want: []model.S3LogEntry{
				{Message: "2024-01-15 ERROR", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
				{Message: "2024-01-15 ERROR", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
				{Message: "2024-01-15 ERROR\n    stacktrace", Source: "s3", SourceCategory: "aws", Service: "s3", Tags: model.Tags{"service:s3"}, Metadata: model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}}},
			},
		},
		"custom_tags_passed_through": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			chanSize: 1,
			rc:       s3RecordContext{tags: model.Tags{"env:prod", "team:aws"}, source: "s3", service: "s3", bucket: "b", key: "k"},
			want: []model.S3LogEntry{{
				Message:        "line1",
				Source:         "s3",
				SourceCategory: "aws",
				Service:        "s3",
				Tags:           model.Tags{"service:s3", "env:prod", "team:aws"},
				Metadata:       model.S3Metadata{S3Context: model.S3Context{Bucket: "b", Key: "k"}},
			}},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			out := make(chan model.S3LogEntry, tc.chanSize)
			ctrl := gomock.NewController(t)
			mock := NewMockS3APIClient(ctrl)
			tc.mockSetup(mock)

			err := processS3Record(context.Background(), mock, out, tc.rc)
			close(out)
			var got []model.S3LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			if tc.wantErr {
				if err == nil {
					t.Fatal("want error, got nil")
				}
				return
			}

			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}
