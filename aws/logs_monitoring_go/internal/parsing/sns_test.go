// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambdacontext"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/google/go-cmp/cmp"
	"go.uber.org/mock/gomock"
)

func TestHandleSNS(t *testing.T) {
	t.Parallel()

	ctx := lambdacontext.NewContext(context.Background(), &lambdacontext.LambdaContext{
		InvokedFunctionArn: "arn:aws:lambda:us-east-1:123456789012:function:forwarder",
	})

	tests := map[string]struct {
		event     json.RawMessage
		config    *config.Config
		mockSetup func(m *MockS3APIClient)
		chanSize  int
		want      []model.S3LogEntry
		wantErr   bool
	}{
		"not an SNS event": {
			event:     json.RawMessage(`{"Records":[]}`),
			config:    &config.Config{},
			mockSetup: func(m *MockS3APIClient) {},
			want:      nil,
		},
		"invalid JSON": {
			event:     json.RawMessage(`not json`),
			config:    &config.Config{},
			mockSetup: func(m *MockS3APIClient) {},
			wantErr:   true,
		},
		"single S3 record via SNS": {
			event: mustSNSEvent(t, mustS3EventJSON(t, "my-bucket", "logs/app.log")),
			config: &config.Config{},
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("hello from s3")),
					}, nil)
			},
			chanSize: 1,
			want: []model.S3LogEntry{{
				Message:        "hello from s3",
				Source:         "s3",
				SourceCategory: "aws",
				Service:        "s3",
				Tags:           model.Tags{"service:s3", "forwardername:", "forwarder_version:6.0"},
				Metadata: model.S3Metadata{
					Metadata:  model.Metadata{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
					S3Context: model.S3Context{Bucket: "my-bucket", Key: "logs/app.log"},
				},
			}},
		},
		"multiple SNS records": {
			event: mustSNSEvent(t,
				mustS3EventJSON(t, "bucket-a", "a.log"),
				mustS3EventJSON(t, "bucket-b", "b.log"),
			),
			config: &config.Config{},
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("from-a")),
					}, nil)
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("from-b")),
					}, nil)
			},
			chanSize: 2,
			want: []model.S3LogEntry{
				{
					Message: "from-a", Source: "s3", SourceCategory: "aws", Service: "s3",
					Tags: model.Tags{"service:s3", "forwardername:", "forwarder_version:6.0"},
					Metadata: model.S3Metadata{
						Metadata:  model.Metadata{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
						S3Context: model.S3Context{Bucket: "bucket-a", Key: "a.log"},
					},
				},
				{
					Message: "from-b", Source: "s3", SourceCategory: "aws", Service: "s3",
					Tags: model.Tags{"service:s3", "forwardername:", "forwarder_version:6.0"},
					Metadata: model.S3Metadata{
						Metadata:  model.Metadata{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
						S3Context: model.S3Context{Bucket: "bucket-b", Key: "b.log"},
					},
				},
			},
		},
		"bad record is skipped": {
			event: mustSNSEventRaw(t, "not valid s3 json", mustS3EventJSON(t, "good-bucket", "good.log")),
			config: &config.Config{},
			mockSetup: func(m *MockS3APIClient) {
				m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
					Return(&s3.GetObjectOutput{
						Body: io.NopCloser(strings.NewReader("survived")),
					}, nil)
			},
			chanSize: 1,
			want: []model.S3LogEntry{{
				Message: "survived", Source: "s3", SourceCategory: "aws", Service: "s3",
				Tags: model.Tags{"service:s3", "forwardername:", "forwarder_version:6.0"},
				Metadata: model.S3Metadata{
					Metadata:  model.Metadata{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
					S3Context: model.S3Context{Bucket: "good-bucket", Key: "good.log"},
				},
			}},
		},
		"s3 fetch error skips record": {
			event: mustSNSEvent(t,
				mustS3EventJSON(t, "fail-bucket", "fail.log"),
				mustS3EventJSON(t, "ok-bucket", "ok.log"),
			),
			config: &config.Config{},
			mockSetup: func(m *MockS3APIClient) {
				gomock.InOrder(
					m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
						Return(nil, errors.New("access denied")),
					m.EXPECT().GetObject(gomock.Any(), gomock.Any()).
						Return(&s3.GetObjectOutput{
							Body: io.NopCloser(strings.NewReader("ok")),
						}, nil),
				)
			},
			chanSize: 1,
			want: []model.S3LogEntry{{
				Message: "ok", Source: "s3", SourceCategory: "aws", Service: "s3",
				Tags: model.Tags{"service:s3", "forwardername:", "forwarder_version:6.0"},
				Metadata: model.S3Metadata{
					Metadata:  model.Metadata{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"},
					S3Context: model.S3Context{Bucket: "ok-bucket", Key: "ok.log"},
				},
			}},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := NewMockS3APIClient(ctrl)
			tc.mockSetup(mock)

			out := make(chan model.S3LogEntry, tc.chanSize)

			var snsEvent events.SNSEvent
			err := json.Unmarshal(tc.event, &snsEvent)
			if err != nil {
				if tc.wantErr {
					return
				}
				t.Fatalf("unexpected unmarshal error: %v", err)
			}
			if tc.wantErr {
				t.Fatal("expected error but unmarshal succeeded")
			}

			metadata := model.Metadata{ARN: "arn:aws:lambda:us-east-1:123456789012:function:forwarder"}
			for _, record := range snsEvent.Records {
				s3Raw := json.RawMessage(record.SNS.Message)
				if err := handleS3Event(ctx, s3Raw, tc.config, mock, metadata, out); err != nil {
					continue
				}
			}
			close(out)

			var got []model.S3LogEntry
			for entry := range out {
				got = append(got, entry)
			}

			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func mustS3EventJSON(t *testing.T, bucket, key string) string {
	t.Helper()

	evt := events.S3Event{
		Records: []events.S3EventRecord{{
			EventSource: "aws:s3",
			S3: events.S3Entity{
				Bucket: events.S3Bucket{Name: bucket},
				Object: events.S3Object{URLDecodedKey: key, Key: key},
			},
		}},
	}

	raw, err := json.Marshal(evt)
	if err != nil {
		t.Fatalf("marshal s3 event: %v", err)
	}

	return string(raw)
}

func mustSNSEvent(t *testing.T, s3Messages ...string) json.RawMessage {
	t.Helper()

	return mustSNSEventRaw(t, s3Messages...)
}

func mustSNSEventRaw(t *testing.T, messages ...string) json.RawMessage {
	t.Helper()

	var evt events.SNSEvent
	for _, msg := range messages {
		evt.Records = append(evt.Records, events.SNSEventRecord{
			EventSource: "aws:sns",
			SNS: events.SNSEntity{
				Type:    "Notification",
				Message: msg,
			},
		})
	}

	raw, err := json.Marshal(evt)
	if err != nil {
		t.Fatalf("marshal sns event: %v", err)
	}

	return raw
}
