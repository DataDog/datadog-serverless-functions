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
	"log/slog"
)

func parseSQS(event json.RawMessage) ([]Event, error) {
	dec := json.NewDecoder(bytes.NewReader(event))
	if err := SkipToRecords(dec); err != nil {
		return nil, fmt.Errorf("skip to records: %w", err)
	}

	var parsed []Event
	for i := 0; dec.More(); i++ {
		body, err := extractBody(dec)
		if err != nil {
			return nil, fmt.Errorf("extract body: %w", err)
		}

		pe, err := parseSQSBody(body)
		if errors.Is(err, errUnknownEvent) {
			slog.Warn("unknown event from SQS record, skipping", slog.Int("index", i))
			continue
		}
		if err != nil {
			return nil, fmt.Errorf("parse body: %w", err)
		}

		parsed = append(parsed, pe)
	}

	if len(parsed) == 0 {
		return nil, errors.New("no recognizable events in SQS batch")
	}
	return parsed, nil
}

func extractBody(dec *json.Decoder) (string, error) {
	if err := SkipBrace(dec); err != nil {
		return "", err
	}

	if err := SkipToKey(dec, "body"); err != nil {
		return "", fmt.Errorf("skip to key: %w", err)
	}

	var body string
	if err := dec.Decode(&body); err != nil {
		return "", fmt.Errorf("decode: %w", err)
	}

	if err := skipToEnd(dec); err != nil {
		return "", fmt.Errorf("skip to end: %w", err)
	}

	return body, nil
}

func parseSQSBody(body string) (Event, error) {
	inner := json.RawMessage(body)
	dec := json.NewDecoder(bytes.NewReader(inner))

	if err := SkipBrace(dec); err != nil {
		return Event{}, err
	}

	var typ, message string
	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return Event{}, err
		}

		switch key {
		case "Type":
			if err := dec.Decode(&typ); err != nil {
				return Event{}, fmt.Errorf("decode: %w", err)
			}
		case "Message":
			if err := dec.Decode(&message); err != nil {
				return Event{}, fmt.Errorf("decode: %w", err)
			}
		case recordsKey:
			if isS3(inner) {
				return Event{ContentType: ContentTypeS3, Payload: inner}, nil
			}
			return Event{}, errUnknownEvent
		default:
			if err := Skip(dec); err != nil {
				return Event{}, err
			}
		}
	}

	if typ == "Notification" && message != "" {
		msg := json.RawMessage(message)
		if isS3(msg) {
			return Event{ContentType: ContentTypeS3, Payload: msg}, nil
		}
		return Event{ContentType: ContentTypeSNS, Payload: inner}, nil
	}

	return Event{}, errUnknownEvent
}
