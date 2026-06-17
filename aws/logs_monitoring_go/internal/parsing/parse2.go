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

type eventDiscriminator struct {
	AWSLogs json.RawMessage `json:"awslogs"` // CloudWatch logs
	Records []struct {
		EventSource string `json:"eventSource"`
	} `json:"Records"` // S3, SQS, SNS
	Detail json.RawMessage `json:"detail"` // EventBridge
	Retry  json.RawMessage `json:"retry"`
}


func ParseUnmarshal(event json.RawMessage) ([]Event, error) {
	var disc eventDiscriminator
	if err := json.Unmarshal(event, &disc); err != nil {
		return nil, err
	}

	switch {
	case disc.AWSLogs != nil:
		return []Event{{ContentType: ContentTypeCloudwatchLogs, Payload: event}}, nil

	case disc.Retry != nil:
		return []Event{{ContentType: ContentTypeRetry}}, nil

	case len(disc.Records) > 0:
		parsed, err := recordsUnmarshal(event, disc)
		if err != nil {
			return nil, fmt.Errorf("records: %w", err)
		}
		return parsed, nil

	case disc.Detail != nil:
		parsed, err := eventBridgeUnmarshal(event)
		if err != nil {
			return nil, fmt.Errorf("eventbridge: %w", err)
		}
		return parsed, nil
	}

	return nil, errors.New("unsupported event")
}

func recordsUnmarshal(event json.RawMessage, disc eventDiscriminator) ([]Event, error) {
	switch disc.Records[0].EventSource {
	case eventSourceS3:
		return []Event{{ContentType: ContentTypeS3, Payload: event}}, nil

	case eventSourceKinesis:
		return []Event{{ContentType: ContentTypeKinesis, Payload: event}}, nil

	case eventSourceSQS:
		parsed, err := sqsUnmarshal(event)
		if err != nil {
			return nil, fmt.Errorf("sqs: %w", err)
		}
		return parsed, nil

	case eventSourceSNS:
		parsed, err := snsUnmarshal(event)
		if err != nil {
			return nil, fmt.Errorf("sns: %w", err)
		}
		return parsed, nil

	default:
		return nil, fmt.Errorf("unsupported event source %q", disc.Records[0].EventSource)
	}
}
