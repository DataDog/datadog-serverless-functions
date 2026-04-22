// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
	"github.com/google/go-cmp/cmp"
)

func TestHandleKinesis(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		event    json.RawMessage
		config   *config.Config
		chanSize int
		want     []model.CloudwatchLogEntry
		wantErr  bool
	}{
		"not a Kinesis event": {
			event:  json.RawMessage(`{"awslogs":{"data":"dGVzdA=="}}`),
			config: &config.Config{},
			want:   nil,
		},
		"invalid JSON": {
			event:   json.RawMessage(`not json`),
			config:  &config.Config{},
			wantErr: true,
		},
		"single log": {
			event: mustKinesisEvent(t, mustGzipJSON(t, map[string]any{
				"messageType": "DATA_MESSAGE",
				"owner":       "601427279990",
				"logGroup":    "/aws/lambda/testing-datadog",
				"logStream":   "2024/10/10/[$LATEST]20bddfd5a2dc4c6b97ac02800eae90d0",
				"logEvents": []map[string]any{
					{"id": "ev1", "timestamp": 1583425836114, "message": `{"status": "debug", "message": "hello"}`},
				},
			})),
			config:   &config.Config{},
			chanSize: 1,
			want: []model.CloudwatchLogEntry{
				{
					ID:             "ev1",
					Timestamp:      1583425836114,
					Message:        `{"status": "debug", "message": "hello"}`,
					Source:         "lambda",
					SourceCategory: "aws",
					Service:        "lambda",
					Host:           "/aws/lambda/testing-datadog",
					Tags:           model.Tags{"service:lambda", "forwardername:", "forwarder_version:6.0"},
					AWS: model.CloudwatchMetadata{
						Metadata: model.Metadata{ARN: testARN},
						Logs: model.CloudwatchLogsContext{
							LogGroup:  "/aws/lambda/testing-datadog",
							LogStream: "2024/10/10/[$LATEST]20bddfd5a2dc4c6b97ac02800eae90d0",
							Owner:     "601427279990",
						},
					},
				},
			},
		},
		"multiple records": {
			event: mustKinesisEvent(t,
				mustGzipJSON(t, map[string]any{
					"messageType": "DATA_MESSAGE",
					"owner":       "111111111111",
					"logGroup":    "/aws/lambda/fn-a",
					"logStream":   "stream-a",
					"logEvents": []map[string]any{
						{"id": "a1", "timestamp": 1000, "message": "from-a"},
					},
				}),
				mustGzipJSON(t, map[string]any{
					"messageType": "DATA_MESSAGE",
					"owner":       "222222222222",
					"logGroup":    "/aws/rds/cluster",
					"logStream":   "stream-b",
					"logEvents": []map[string]any{
						{"id": "b1", "timestamp": 2000, "message": "from-b"},
					},
				}),
			),
			config:   &config.Config{},
			chanSize: 2,
			want: []model.CloudwatchLogEntry{
				{
					ID: "a1", Timestamp: 1000, Message: "from-a",
					Source: "lambda", SourceCategory: "aws", Service: "lambda",
					Host: "/aws/lambda/fn-a",
					Tags: model.Tags{"service:lambda", "forwardername:", "forwarder_version:6.0"},
					AWS: model.CloudwatchMetadata{
						Metadata: model.Metadata{ARN: testARN},
						Logs:     model.CloudwatchLogsContext{LogGroup: "/aws/lambda/fn-a", LogStream: "stream-a", Owner: "111111111111"},
					},
				},
				{
					ID: "b1", Timestamp: 2000, Message: "from-b",
					Source: "cloudwatch", SourceCategory: "aws", Service: "cloudwatch",
					Host: "/aws/rds/cluster",
					Tags: model.Tags{"service:cloudwatch", "forwardername:", "forwarder_version:6.0"},
					AWS: model.CloudwatchMetadata{
						Metadata: model.Metadata{ARN: testARN},
						Logs:     model.CloudwatchLogsContext{LogGroup: "/aws/rds/cluster", LogStream: "stream-b", Owner: "222222222222"},
					},
				},
			},
		},
		"bad record is skipped": {
			event: mustKinesisEvent(t,
				[]byte("not valid gzip"),
				mustGzipJSON(t, map[string]any{
					"messageType": "DATA_MESSAGE",
					"owner":       "123456789012",
					"logGroup":    "/aws/lambda/good",
					"logStream":   "stream",
					"logEvents": []map[string]any{
						{"id": "g1", "timestamp": 3000, "message": "survived"},
					},
				}),
			),
			config:   &config.Config{},
			chanSize: 1,
			want: []model.CloudwatchLogEntry{
				{
					ID: "g1", Timestamp: 3000, Message: "survived",
					Source: "lambda", SourceCategory: "aws", Service: "lambda",
					Host: "/aws/lambda/good",
					Tags: model.Tags{"service:lambda", "forwardername:", "forwarder_version:6.0"},
					AWS: model.CloudwatchMetadata{
						Metadata: model.Metadata{ARN: testARN},
						Logs:     model.CloudwatchLogsContext{LogGroup: "/aws/lambda/good", LogStream: "stream", Owner: "123456789012"},
					},
				},
			},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			out := make(chan model.CloudwatchLogEntry, tc.chanSize)

			err := HandleKinesis(testLambdaCtx, tc.event, tc.config, out)
			close(out)

			var got []model.CloudwatchLogEntry
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

func mustKinesisEvent(t *testing.T, records ...[]byte) json.RawMessage {
	t.Helper()

	var evt events.KinesisEvent
	for _, data := range records {
		evt.Records = append(evt.Records, events.KinesisEventRecord{
			Kinesis: events.KinesisRecord{
				Data: data,
			},
		})
	}

	raw, err := json.Marshal(evt)
	if err != nil {
		t.Fatalf("marshal kinesis event: %v", err)
	}

	return raw
}
