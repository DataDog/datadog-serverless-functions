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

	"github.com/aws/aws-lambda-go/events"
)

const (
	eventBridgeSourceS3     = "aws.s3"
	eventBridgeDetailTypeS3 = "Object Created"
)

func parseEventBridge(event json.RawMessage) ([]ParsedEvent, error) {
	source, detailType, detail, err := decodeEventBridgeEnvelope(event)
	if err != nil {
		return nil, fmt.Errorf("decode eventbridge: %w", err)
	}

	if source == eventBridgeSourceS3 && strings.Contains(detailType, eventBridgeDetailTypeS3) {
		s3Event, err := buildS3EventFromEventBridge(detail)
		if err != nil {
			return nil, fmt.Errorf("build s3 event from eventbridge: %w", err)
		}
		return []ParsedEvent{{ContentTypeS3, s3Event}}, nil
	}

	return []ParsedEvent{{ContentTypeEventBridge, event}}, nil
}

func decodeEventBridgeEnvelope(event json.RawMessage) (source, detailType string, detail json.RawMessage, err error) {
	dec := json.NewDecoder(bytes.NewReader(event))

	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return "", "", nil, errors.New("eventbridge envelope: expected '{'")
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return "", "", nil, fmt.Errorf("read key: %w", err)
		}
		switch key {
		case "source":
			if err := dec.Decode(&source); err != nil {
				return "", "", nil, fmt.Errorf("decode source: %w", err)
			}
		case "detail-type":
			if err := dec.Decode(&detailType); err != nil {
				return "", "", nil, fmt.Errorf("decode detail-type: %w", err)
			}
		case "detail":
			if err := dec.Decode(&detail); err != nil {
				return "", "", nil, fmt.Errorf("decode detail: %w", err)
			}
		default:
			var skip json.RawMessage
			if err := dec.Decode(&skip); err != nil {
				return "", "", nil, fmt.Errorf("skip field: %w", err)
			}
		}
	}

	return source, detailType, detail, nil
}

func buildS3EventFromEventBridge(detail json.RawMessage) (json.RawMessage, error) {
	bucketName, objectKey, err := decodeEventBridgeS3Detail(detail)
	if err != nil {
		return nil, fmt.Errorf("decode eventbridge s3 detail: %w", err)
	}

	s3Event := events.S3Event{
		Records: []events.S3EventRecord{{
			EventSource: eventSourceS3,
			S3: events.S3Entity{
				Bucket: events.S3Bucket{Name: bucketName},
				Object: events.S3Object{Key: objectKey, URLDecodedKey: objectKey},
			},
		}},
	}
	payload, err := json.Marshal(s3Event)
	if err != nil {
		return nil, fmt.Errorf("marshal synthetic s3 event: %w", err)
	}
	return payload, nil
}

func decodeEventBridgeS3Detail(detail json.RawMessage) (bucket, key string, err error) {
	dec := json.NewDecoder(bytes.NewReader(detail))

	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return "", "", errors.New("eventbridge s3 detail: expected '{'")
	}

	for dec.More() {
		k, err := dec.Token()
		if err != nil {
			return "", "", fmt.Errorf("read key: %w", err)
		}
		switch k {
		case "bucket":
			var b struct {
				Name string `json:"name"`
			}
			if err := dec.Decode(&b); err != nil {
				return "", "", fmt.Errorf("decode bucket: %w", err)
			}
			bucket = b.Name
		case "object":
			var o struct {
				Key string `json:"key"`
			}
			if err := dec.Decode(&o); err != nil {
				return "", "", fmt.Errorf("decode object: %w", err)
			}
			key = o.Key
		default:
			var skip json.RawMessage
			if err := dec.Decode(&skip); err != nil {
				return "", "", fmt.Errorf("skip field: %w", err)
			}
		}
	}

	return bucket, key, nil
}
