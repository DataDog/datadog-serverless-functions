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
	eventSourceSNS     = "aws:sns"
)

func Parse(event json.RawMessage) ([]ParsedEvent, error) {
	dec := json.NewDecoder(bytes.NewReader(event))
	if err := skipBrace(dec); err != nil {
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
				return nil, fmt.Errorf("records: %w")
			}
			return parsed, nil
		case detailKey:
			parsed, err := parseEventBridge(event)
			if err != nil {
				return nil, fmt.Errorf("eventbridge: %w")
			}
			return parsed, nil
		default:
			if err := skip(dec); err != nil {
				return nil, fmt.Errorf("decode: %w", err)
			}
		}
	}

	return nil, errors.New("unsupported event")
}

func parseRecords(event json.RawMessage, dec *json.Decoder) ([]ParsedEvent, error) {
	if err := skipBracket(dec); err != nil {
		return nil, err
	}
	if err := skipBrace(dec); err != nil {
		return nil, err
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return nil, err
		}

		if !strings.EqualFold(key.(string), eventSourceKey) { // SNS event source key has a capital letter
			var skip json.RawMessage
			if err := dec.Decode(&skip); err != nil {
				return nil, fmt.Errorf("decode: %w", err)
			}
			continue
		}

		val, err := dec.Token()
		if err != nil {
			return nil, err
		}

		eventSource, ok := val.(string)
		if !ok {
			return nil, fmt.Errorf("eventSource value should be a string: %v", val)
		}

		switch eventSource {
		case eventSourceS3:
			return []ParsedEvent{{ContentType: ContentTypeS3, Payload: event}}, nil
		case eventSourceKinesis:
			return []ParsedEvent{{ContentType: ContentTypeKinesis, Payload: event}}, nil
		case eventSourceSNS:
			return parseSNS(event)
		default:
			return nil, fmt.Errorf("unsupported event source %q", eventSource)
		}
	}

	return nil, errors.New("no eventSource found")
}

func skipBrace(dec *json.Decoder) error {
	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return errors.New("expected '{'")
	}
	return nil
}

func skipBracket(dec *json.Decoder) error {
	if t, err := dec.Token(); err != nil || t != json.Delim('[') {
		return errors.New("expected '['")
	}
	return nil
}

func skipToKey(dec *json.Decoder, key string) error {
	for dec.More() {
		k, err := dec.Token()
		if err != nil {
			return err
		}

		if k != key {
			if err := skip(dec); err != nil {
				return err
			}
			continue
		}

		return nil
	}

	return &KeyNotFoundError{key}
}

func skipToRecords(dec *json.Decoder) error {
	if err := skipBrace(dec); err != nil {
		return err
	}

	if err := skipToKey(dec, recordsKey); err != nil {
		return err
	}

	if err := skipBracket(dec); err != nil {
		return err
	}
	return nil
}

func skipToEnd(dec *json.Decoder) error {
	for dec.More() {
		if err := skip(dec); err != nil {
			return err
		}
	}

	_, err := dec.Token()
	return err
}

func skip(dec *json.Decoder) error {
	var skip json.RawMessage
	if err := dec.Decode(&skip); err != nil {
		return fmt.Errorf("skip: %w", err)
	}
	return nil
}
