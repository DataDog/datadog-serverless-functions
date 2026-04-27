// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
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

var testS3Metadata = model.S3Metadata{
	Origin: model.S3Origin{Bucket: "b", Key: "k"},
}

func TestProcessS3Record(t *testing.T) {
	tests := map[string]struct {
		mockSetup func(m *MockS3APIClient)
		chanSize  int
		base      s3EntryBase
		want      []model.LogEntry
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
			base:     newTestS3Base(),
			want:     []model.LogEntry{wantS3Entry("line1", "s3", "s3", model.Tags{"service:s3"})},
		},
		"multiple_lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1\nline2\nline3")),
					}, nil)
			},
			chanSize: 3,
			base:     newTestS3Base(),
			want: []model.LogEntry{
				wantS3Entry("line1", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("line2", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("line3", "s3", "s3", model.Tags{"service:s3"}),
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
			base:     newTestS3Base(),
			want:     nil,
		},
		"s3_error": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("access denied"))
			},
			chanSize: 1,
			base:     newTestS3Base(),
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
			base:     newTestS3Base(),
			want:     []model.LogEntry{wantS3Entry(`{"msg":"hello"}`, "s3", "myapp", model.Tags{"env:prod", "service:myapp"})},
		},
		"invalid_utf8_stripped": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("hello\x80world")),
					}, nil)
			},
			chanSize: 1,
			base:     newTestS3Base(),
			want:     []model.LogEntry{wantS3Entry("helloworld", "s3", "s3", model.Tags{"service:s3"})},
		},
		"multiline_groups_continuation_lines": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n2024-01-15 INFO started")),
					}, nil)
			},
			chanSize: 2,
			base: newTestS3Base(func(b *s3EntryBase) {
				b.multilineRegex = regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)
			}),
			want: []model.LogEntry{
				wantS3Entry("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("2024-01-15 INFO started", "s3", "s3", model.Tags{"service:s3"}),
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
			base: newTestS3Base(func(b *s3EntryBase) {
				b.multilineRegex = regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)
			}),
			want: []model.LogEntry{wantS3Entry("2024-01-15 ERROR\n    stacktrace", "s3", "s3", model.Tags{"service:s3"})},
		},
		"multimatch_single_line": {
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR2024-01-15 ERROR2024-01-15 ERROR\n    stacktrace")),
					}, nil)
			},
			chanSize: 3,
			base: newTestS3Base(func(b *s3EntryBase) {
				b.multilineRegex = regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)
			}),
			want: []model.LogEntry{
				wantS3Entry("2024-01-15 ERROR", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("2024-01-15 ERROR", "s3", "s3", model.Tags{"service:s3"}),
				wantS3Entry("2024-01-15 ERROR\n    stacktrace", "s3", "s3", model.Tags{"service:s3"}),
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
			base: newTestS3Base(func(b *s3EntryBase) {
				b.tags = model.Tags{"env:prod", "team:aws"}
			}),
			want: []model.LogEntry{wantS3Entry("line1", "s3", "s3", model.Tags{"service:s3", "env:prod", "team:aws"})},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			out := make(chan model.LogEntry, tc.chanSize)
			ctrl := gomock.NewController(t)
			mock := NewMockS3APIClient(ctrl)
			tc.mockSetup(mock)

			err := processS3Record(t.Context(), mock, out, tc.base)
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

			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func newTestS3Base(opts ...func(*s3EntryBase)) s3EntryBase {
	base := s3EntryBase{
		metadata: testS3Metadata,
		source:   "s3",
		service:  "s3",
		tags:     model.Tags{},
	}
	for _, o := range opts {
		o(&base)
	}
	return base
}

func wantS3Entry(message, source, service string, tags model.Tags) model.LogEntry {
	return model.NewLogEntry(testS3Metadata, tags, message, source, service)
}
