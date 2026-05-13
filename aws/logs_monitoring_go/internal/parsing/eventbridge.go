// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bytes"
	"encoding/json"
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
		return []ParsedEvent{{ContentType: ContentTypeS3, Payload: s3Event}}, nil
	}

	return []ParsedEvent{{ContentType: ContentTypeEventBridge, Payload: event}}, nil
}

func decodeEventBridgeEnvelope(event json.RawMessage) (source, detailType string, detail json.RawMessage, err error) {
	dec := json.NewDecoder(bytes.NewReader(event))
	if err := skipBrace(dec); err != nil {
		return "", "", nil, err
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return "", "", nil, fmt.Errorf("read key: %w", err)
		}

		switch key {
		case "source":
			if err := dec.Decode(&source); err != nil {
				return "", "", nil, fmt.Errorf("source: %w", err)
			}
		case "detail-type":
			if err := dec.Decode(&detailType); err != nil {
				return "", "", nil, fmt.Errorf("detail-type: %w", err)
			}
		case "detail":
			if err := dec.Decode(&detail); err != nil {
				return "", "", nil, fmt.Errorf("detail: %w", err)
			}
		default:
			if err := skip(dec); err != nil {
				return "", "", nil, err
			}
		}
	}

	return source, detailType, detail, nil
}

func buildS3EventFromEventBridge(detail json.RawMessage) (json.RawMessage, error) {
	bucketName, objectKey, err := decodeEventBridgeS3Detail(detail)
	if err != nil {
		return nil, fmt.Errorf("decode: %w", err)
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
		return nil, fmt.Errorf("marshal: %w", err)
	}
	return payload, nil
}

func decodeEventBridgeS3Detail(detail json.RawMessage) (bucket, key string, err error) {
	dec := json.NewDecoder(bytes.NewReader(detail))

	if err := skipBrace(dec); err != nil {
		return "", "", err
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
				return "", "", fmt.Errorf("bucket: %w", err)
			}
			bucket = b.Name
		case "object":
			var o struct {
				Key string `json:"key"`
			}
			if err := dec.Decode(&o); err != nil {
				return "", "", fmt.Errorf("object: %w", err)
			}
			key = o.Key
		default:
			if err := skip(dec); err != nil {
				return "", "", err
			}
		}
	}

	return bucket, key, nil
}
