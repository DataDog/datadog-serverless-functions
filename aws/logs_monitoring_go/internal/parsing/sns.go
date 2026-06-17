// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bytes"
	"encoding/json"
	"fmt"
)

func parseSNS(event json.RawMessage) ([]Event, error) {
	dec := json.NewDecoder(bytes.NewReader(event))

	if err := SkipToRecords(dec); err != nil {
		return nil, fmt.Errorf("skip to records: %w", err)
	}

	var parsed []Event
	for dec.More() {
		var record json.RawMessage
		if err := dec.Decode(&record); err != nil {
			return nil, fmt.Errorf("decode: %w", err)
		}

		recDec := json.NewDecoder(bytes.NewReader(record))
		if err := SkipBrace(recDec); err != nil {
			return nil, err
		}
		if err := SkipToKey(recDec, "Sns"); err != nil {
			return nil, fmt.Errorf("skip to key: %w", err)
		}
		if err := SkipBrace(recDec); err != nil {
			return nil, err
		}
		if err := SkipToKey(recDec, "Message"); err != nil {
			return nil, fmt.Errorf("skip to key: %w", err)
		}

		var message string
		if err := recDec.Decode(&message); err != nil {
			return nil, fmt.Errorf("decode: %w", err)
		}

		inner := json.RawMessage(message)
		if isS3(inner) {
			parsed = append(parsed, Event{ContentType: ContentTypeS3, Payload: inner})
			continue
		}

		parsed = append(parsed, Event{ContentType: ContentTypeSNS, Payload: record})
	}

	return parsed, nil
}

func isS3(message json.RawMessage) bool {
	dec := json.NewDecoder(bytes.NewReader(message))

	if err := SkipToRecords(dec); err != nil {
		return false
	}

	if err := SkipBrace(dec); err != nil {
		return false
	}

	return SkipToKey(dec, "s3") == nil
}
