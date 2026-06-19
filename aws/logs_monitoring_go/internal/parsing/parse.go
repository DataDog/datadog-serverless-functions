// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"errors"
	"fmt"
)

const (
	eventSourceS3      = "aws:s3"
	eventSourceKinesis = "aws:kinesis"
	eventSourceSQS     = "aws:sqs"
	eventSourceSNS     = "aws:sns"
)

type eventDiscriminator struct {
	AWSLogs json.RawMessage `json:"awslogs"` // CloudWatch logs
	recordsDiscriminator
	Detail json.RawMessage `json:"detail"` // EventBridge
	Retry  json.RawMessage `json:"retry"`
}

type recordsDiscriminator struct {
	Records []struct {
		EventSource string `json:"eventSource"`
	} `json:"Records"` // S3, SQS, SNS
}

func Parse(event json.RawMessage) (Event, error) {
	var disc eventDiscriminator
	if err := json.Unmarshal(event, &disc); err != nil {
		return Event{}, fmt.Errorf("unmarshal: %w", err)
	}

	switch {
	case disc.AWSLogs != nil:
		return Event{ContentType: ContentTypeCloudwatchLogs, Payload: event}, nil

	case disc.Retry != nil:
		return Event{ContentType: ContentTypeRetry}, nil

	case len(disc.Records) > 0:
		event, err := records(event, disc)
		if err != nil {
			return Event{}, fmt.Errorf("records: %w", err)
		}
		return event, nil

	case disc.Detail != nil:
		event, err := eventBridge(event)
		if err != nil {
			return Event{}, fmt.Errorf("eventbridge: %w", err)
		}
		return event, nil
	}

	return Event{}, errors.New("unsupported event")
}

func records(event json.RawMessage, disc eventDiscriminator) (Event, error) {
	switch disc.Records[0].EventSource {
	case eventSourceS3:
		return Event{ContentType: ContentTypeS3, Payload: event}, nil

	case eventSourceKinesis:
		return Event{ContentType: ContentTypeKinesis, Payload: event}, nil

	case eventSourceSNS:
		event, err := sns(event)
		if err != nil {
			return Event{}, fmt.Errorf("sns: %w", err)
		}
		return event, nil

	default:
		return Event{}, fmt.Errorf("unsupported event source %q", disc.Records[0].EventSource)
	}
}
