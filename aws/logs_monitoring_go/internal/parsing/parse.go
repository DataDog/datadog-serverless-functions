// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

const (
	eventSourceKey     = "eventSource"
	eventSourceS3      = "aws:s3"
	eventSourceKinesis = "aws:kinesis"
)

func Parse(event json.RawMessage) ([]ParsedEvent, error) {
	dec := json.NewDecoder(bytes.NewReader(event))

	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return nil, errors.New("expected JSON object")
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return nil, fmt.Errorf("read key: %w", err)
		}

		switch key {
		case "awslogs":
			return []ParsedEvent{{ContentType: ContentTypeCloudwatchLogs, Payload: event}}, nil
		case "Records":
			return parseRecords(event, dec)
		case "detail":
			return parseEventBridge(event)
		default:
			var skip json.RawMessage
			if err := dec.Decode(&skip); err != nil {
				return nil, fmt.Errorf("skip value: %w", err)
			}
		}
	}

	return nil, errors.New("unsupported event")
}

func parseRecords(event json.RawMessage, dec *json.Decoder) ([]ParsedEvent, error) {
	if t, err := dec.Token(); err != nil || t != json.Delim('[') {
		return nil, errors.New("records: expected array")
	}
	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return nil, errors.New("records: expected object")
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return nil, fmt.Errorf("read record key: %w", err)
		}

		if !strings.EqualFold(key.(string), eventSourceKey) { // SNS has EventSource, others have eventSource
			var skip json.RawMessage
			if err := dec.Decode(&skip); err != nil {
				return nil, fmt.Errorf("skip record field: %w", err)
			}
			continue
		}

		val, err := dec.Token()
		if err != nil {
			return nil, fmt.Errorf("read event source value: %w", err)
		}

		eventSource, ok := val.(string)
		if !ok {
			return nil, fmt.Errorf("eventSource is not a string: %v", val)
		}

		switch eventSource {
		case eventSourceS3:
			return []ParsedEvent{{ContentType: ContentTypeS3, Payload: event}}, nil
		case eventSourceKinesis:
			return []ParsedEvent{{ContentType: ContentTypeKinesis, Payload: event}}, nil
		default:
			return nil, fmt.Errorf("records: unsupported event source %q", eventSource)
		}
	}

	return nil, errors.New("no eventSource found in records")
}
