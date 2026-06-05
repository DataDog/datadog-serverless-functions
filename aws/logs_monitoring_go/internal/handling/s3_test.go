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

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
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

	testVpcFlowLogsKey         = "AWSLogs/123456789012/vpcflowlogs/us-east-1/2024/01/01/log.log.gz"
	testVpcFlowLogsEventRecord = events.S3EventRecord{
		S3: events.S3Entity{
			Bucket: events.S3Bucket{Name: "vpc-bucket"},
			Object: events.S3Object{URLDecodedKey: testVpcFlowLogsKey},
		},
	}

	testWAFKey         = "AWSLogs/123456779121/WAFLogs/us-east-1/webacl/aws-waf-logs-example.log.gz"
	testWAFEventRecord = events.S3EventRecord{
		S3: events.S3Entity{
			Bucket: events.S3Bucket{Name: "waf-bucket"},
			Object: events.S3Object{URLDecodedKey: testWAFKey},
		},
	}
)

func TestProcessS3Record(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		mockSetup   func(m *sdkclient.MockS3)
		cfg         *Config
		filterer    *filtering.Filterer
		eventRecord events.S3EventRecord
		want        []model.LogEntry
		wantErr     bool
	}{
		"single line": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("line1", "s3", "s3", nil)},
		},
		"multiple lines": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1\nline2\nline3")),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testS3EventRecord,
			want: []model.LogEntry{
				wantS3Entry("line1", "s3", "s3", nil),
				wantS3Entry("line2", "s3", "s3", nil),
				wantS3Entry("line3", "s3", "s3", nil),
			},
		},
		"empty file": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("")),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testS3EventRecord,
			want:        nil,
		},
		"s3 error": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(nil, errors.New("access denied"))
			},
			cfg:         &Config{},
			eventRecord: testS3EventRecord,
			wantErr:     true,
		},
		"ddtags extraction": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader(`{"ddtags":"env:prod,service:myapp","msg":"hello"}`)),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry(`{"msg":"hello"}`, "s3", "myapp", model.Tags{"env:prod"})},
		},
		"invalid utf8 stripped": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("hello\x80world")),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("helloworld", "s3", "s3", nil)},
		},
		"multiline groups continuation lines": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n2024-01-15 INFO started")),
					}, nil)
			},
			cfg:         &Config{S3MultilineLogRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
			eventRecord: testS3EventRecord,
			want: []model.LogEntry{
				wantS3Entry("2024-01-15 ERROR NullPointer\n    at com.foo.Bar\n", "s3", "s3", nil),
				wantS3Entry("2024-01-15 INFO started", "s3", "s3", nil),
			},
		},
		"multiline flushes at eof": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("2024-01-15 ERROR\n    stacktrace")),
					}, nil)
			},
			cfg:         &Config{S3MultilineLogRegex: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("2024-01-15 ERROR\n    stacktrace", "s3", "s3", nil)},
		},
		"custom tags passed through": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("line1")),
					}, nil)
			},
			cfg:         &Config{Tags: model.Tags{"env:prod", "team:aws"}},
			eventRecord: testS3EventRecord,
			want:        []model.LogEntry{wantS3Entry("line1", "s3", "s3", model.Tags{"env:prod", "team:aws"})},
		},
		"cloudtrail with ec2 host": {
			mockSetup: func(m *sdkclient.MockS3) {
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
			cfg:         &Config{},
			eventRecord: testCloudTrailEventRecord,
			want: []model.LogEntry{
				wantCloudTrailEntry(
					`{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:sts::601427279990:assumed-role/MyRole/i-08014e4f62ccf762d"}}`,
					"i-08014e4f62ccf762d",
				),
			},
		},
		"cloudtrail without ec2 host": {
			mockSetup: func(m *sdkclient.MockS3) {
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
			cfg:         &Config{},
			eventRecord: testCloudTrailEventRecord,
			want: []model.LogEntry{
				wantCloudTrailEntry(
					`{"eventName":"DescribeTable","userIdentity":{"arn":"arn:aws:iam::601427279990:user/admin"}}`,
					"",
				),
			},
		},
		"vpc flow logs skips header line": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("version account-id interface-id srcaddr dstaddr srcport dstport protocol\n2 123456789012 eni-abc123 10.0.0.1 10.0.0.2 443 49152 6\n2 123456789012 eni-abc123 10.0.0.2 10.0.0.1 49152 443 6")),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testVpcFlowLogsEventRecord,
			want: []model.LogEntry{
				wantVpcFlowLogsEntry("2 123456789012 eni-abc123 10.0.0.1 10.0.0.2 443 49152 6"),
				wantVpcFlowLogsEntry("2 123456789012 eni-abc123 10.0.0.2 10.0.0.1 49152 443 6"),
			},
		},
		"waf single line": {
			mockSetup: func(m *sdkclient.MockS3) {
				data := testutil.MustGzip(t, []byte(`{"httpRequest":{"headers":[{"name":"Host","value":"example.com"}]}}`))
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(bytes.NewReader(data)),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testWAFEventRecord,
			want:        []model.LogEntry{wantWAFEntry(`{"httpRequest":{"headers":{"Host":"example.com"}}}`)},
		},
		"waf multiple lines": {
			mockSetup: func(m *sdkclient.MockS3) {
				lines := `{"httpRequest":{"headers":[{"name":"h1","value":"v1"}]}}` + "\n" +
					`{"httpRequest":{"headers":[{"name":"h2","value":"v2"}]}}`
				data := testutil.MustGzip(t, []byte(lines))
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(bytes.NewReader(data)),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testWAFEventRecord,
			want: []model.LogEntry{
				wantWAFEntry(`{"httpRequest":{"headers":{"h1":"v1"}}}`),
				wantWAFEntry(`{"httpRequest":{"headers":{"h2":"v2"}}}`),
			},
		},
		"waf does not apply multiline regex": {
			mockSetup: func(m *sdkclient.MockS3) {
				lines := `{"action":"ALLOW"}` + "\n" + `{"action":"BLOCK"}`
				data := testutil.MustGzip(t, []byte(lines))
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(bytes.NewReader(data)),
					}, nil)
			},
			cfg:         &Config{S3MultilineLogRegex: regexp.MustCompile(`\{`)},
			eventRecord: testWAFEventRecord,
			want: []model.LogEntry{
				wantWAFEntry(`{"action":"ALLOW"}`),
				wantWAFEntry(`{"action":"BLOCK"}`),
			},
		},
		"waf non-gzipped": {
			mockSetup: func(m *sdkclient.MockS3) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader(`{"httpRequest":{"headers":[{"name":"Host","value":"example.com"}]}}`)),
					}, nil)
			},
			cfg:         &Config{},
			eventRecord: testWAFEventRecord,
			want:        []model.LogEntry{wantWAFEntry(`{"httpRequest":{"headers":{"Host":"example.com"}}}`)},
		},
		"waf exclude at match": {
			mockSetup: func(m *sdkclient.MockS3) {
				lines := `{"action":"ALLOW","httpRequest":{}}` + "\n" + `{"action":"BLOCK","httpRequest":{}}`
				data := testutil.MustGzip(t, []byte(lines))
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(bytes.NewReader(data)),
					}, nil)
			},
			cfg:         &Config{},
			filterer:    filtering.NewFilterer(nil, regexp.MustCompile(`"action":"BLOCK"`)),
			eventRecord: testWAFEventRecord,
			want:        []model.LogEntry{wantWAFEntry(`{"action":"ALLOW","httpRequest":{}}`)},
		},
		"waf include at match": {
			mockSetup: func(m *sdkclient.MockS3) {
				lines := `{"action":"ALLOW","httpRequest":{}}` + "\n" + `{"action":"BLOCK","httpRequest":{}}`
				data := testutil.MustGzip(t, []byte(lines))
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(bytes.NewReader(data)),
					}, nil)
			},
			cfg:         &Config{},
			filterer:    filtering.NewFilterer(regexp.MustCompile(`"action":"ALLOW"`), nil),
			eventRecord: testWAFEventRecord,
			want:        []model.LogEntry{wantWAFEntry(`{"action":"ALLOW","httpRequest":{}}`)},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := sdkclient.NewMockS3(ctrl)
			tc.mockSetup(mock)

			out := make(chan model.LogEntry, len(tc.want))
			handler := newS3(tc.cfg, mock, nil, tc.filterer)

			err := handler.processRecord(t.Context(), out, tc.eventRecord, testutil.LambdaOrigin())
			close(out)

			var got []model.LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
			assert.Equal(t, tc.want, got)
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

func wantVpcFlowLogsEntry(message string) model.LogEntry {
	entry := model.NewLogEntry()
	entry.Message = message
	entry.Source = sourceS3
	entry.Service = sourceS3
	entry.Metadata = model.S3Metadata{
		LambdaOrigin: testutil.LambdaOrigin(),
		Origin:       model.S3Origin{Bucket: "vpc-bucket", Key: testVpcFlowLogsKey},
	}
	return entry
}

func wantWAFEntry(message string) model.LogEntry {
	entry := model.NewLogEntry()
	entry.Message = message
	entry.Source = sourceWAF
	entry.Service = sourceWAF
	entry.Metadata = model.S3Metadata{
		LambdaOrigin: testutil.LambdaOrigin(),
		Origin:       model.S3Origin{Bucket: "waf-bucket", Key: testWAFKey},
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
