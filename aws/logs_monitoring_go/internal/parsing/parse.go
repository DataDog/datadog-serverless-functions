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
	cloudwatchLogsKey = "awslogs"
	detailKey         = "detail"
	eventSourceKey    = "eventSource"
	recordsKey        = "Records"

	eventSourceS3      = "aws:s3"
	eventSourceKinesis = "aws:kinesis"
	eventSourceSQS     = "aws:sqs"
	eventSourceSNS     = "aws:sns"
)

func Parse(event json.RawMessage) ([]ParsedEvent, error) {
	dec := json.NewDecoder(bytes.NewReader(event))
	if err := SkipBrace(dec); err != nil {
		return nil, err
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return nil, err
		}

		switch key {
		case cloudwatchLogsKey:
			return []ParsedEvent{{ContentType: ContentTypeCloudwatchLogs, Payload: event}}, nil
		case recordsKey:
			parsed, err := parseRecords(event, dec)
			if err != nil {
				return nil, fmt.Errorf("records: %w", err)
			}
			return parsed, nil
		case detailKey:
			parsed, err := parseEventBridge(event)
			if err != nil {
				return nil, fmt.Errorf("eventbridge: %w", err)
			}
			return parsed, nil
		default:
			if err := Skip(dec); err != nil {
				return nil, err
			}
		}
	}

	return nil, errors.New("unsupported event")
}

func parseRecords(event json.RawMessage, dec *json.Decoder) ([]ParsedEvent, error) {
	if err := SkipBracket(dec); err != nil {
		return nil, err
	}
	if err := SkipBrace(dec); err != nil {
		return nil, err
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return nil, err
		}

		keyStr, ok := key.(string)
		if !ok {
			return nil, fmt.Errorf("expected string key, got %T", key)
		}

		// SNS uses "EventSource" so we compare case-insensitively.
		if !strings.EqualFold(keyStr, eventSourceKey) {
			if err := Skip(dec); err != nil {
				return nil, err
			}
			continue
		}

		val, err := dec.Token()
		if err != nil {
			return nil, err
		}

		eventSource, ok := val.(string)
		if !ok {
			return nil, fmt.Errorf("eventSource value should be a string, got %T", val)
		}

		switch eventSource {
		case eventSourceS3:
			return []ParsedEvent{{ContentType: ContentTypeS3, Payload: event}}, nil
		case eventSourceKinesis:
			return []ParsedEvent{{ContentType: ContentTypeKinesis, Payload: event}}, nil
		case eventSourceSQS:
			parsed, err := parseSQS(event)
			if err != nil {
				return nil, fmt.Errorf("sqs: %w", err)
			}
			return parsed, nil
		case eventSourceSNS:
			parsed, err := parseSNS(event)
			if err != nil {
				return nil, fmt.Errorf("sns: %w", err)
			}
			return parsed, nil
		default:
			return nil, fmt.Errorf("unsupported event source %q", eventSource)
		}
	}

	return nil, errors.New("no eventSource found")
}

func SkipBrace(dec *json.Decoder) error {
	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return fmt.Errorf("expected '{': %w", err)
	}
	return nil
}

func SkipBracket(dec *json.Decoder) error {
	if t, err := dec.Token(); err != nil || t != json.Delim('[') {
		return fmt.Errorf("expected '[': %w", err)
	}
	return nil
}

func SkipToKey(dec *json.Decoder, key string) error {
	for dec.More() {
		k, err := dec.Token()
		if err != nil {
			return err
		}

		if k != key {
			if err := Skip(dec); err != nil {
				return err
			}
			continue
		}

		return nil
	}

	return &KeyNotFoundError{key}
}

func SkipToRecords(dec *json.Decoder) error {
	if err := SkipBrace(dec); err != nil {
		return err
	}

	if err := SkipToKey(dec, recordsKey); err != nil {
		return err
	}

	if err := SkipBracket(dec); err != nil {
		return err
	}
	return nil
}

func Skip(dec *json.Decoder) error {
	var skip json.RawMessage
	if err := dec.Decode(&skip); err != nil {
		return fmt.Errorf("skip: %w", err)
	}
	return nil
}

func skipToEnd(dec *json.Decoder) error {
	for dec.More() {
		if _, err := dec.Token(); err != nil {
			return err
		}
		if err := skip(dec); err != nil {
			return err
		}
	}
	_, err := dec.Token()
	return err
}
