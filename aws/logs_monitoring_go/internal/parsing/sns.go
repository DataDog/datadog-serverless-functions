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

func parseSNS(event json.RawMessage) ([]ParsedEvent, error) {
	dec := json.NewDecoder(bytes.NewReader(event))

	if err := skipToRecords(dec); err != nil {
		return nil, fmt.Errorf("skip to records: %w", err)
	}

	var parsed []ParsedEvent
	for dec.More() {
		var record json.RawMessage
		if err := dec.Decode(&record); err != nil {
			return nil, fmt.Errorf("decode: %w", err)
		}

		recDec := json.NewDecoder(bytes.NewReader(record))
		if err := skipBrace(recDec); err != nil {
			return nil, err
		}
		if err := skipToKey(recDec, "Sns"); err != nil {
			return nil, fmt.Errorf("skip to key: %w", err)
		}
		if err := skipBrace(recDec); err != nil {
			return nil, err
		}
		if err := skipToKey(recDec, "Message"); err != nil {
			return nil, fmt.Errorf("skip to key: %w", err)
		}

		var message string
		if err := recDec.Decode(&message); err != nil {
			return nil, fmt.Errorf("decode: %w", err)
		}

		inner := json.RawMessage(message)
		if isS3(inner) {
			parsed = append(parsed, ParsedEvent{ContentTypeS3, inner})
			continue
		}

		parsed = append(parsed, ParsedEvent{ContentTypeSNS, record})
	}

	return parsed, nil
}

func isS3(message json.RawMessage) bool {
	dec := json.NewDecoder(bytes.NewReader(message))

	if err := skipToRecords(dec); err != nil {
		return false
	}

	if err := skipBrace(dec); err != nil {
		return false
	}

	return skipToKey(dec, "s3") == nil
}
