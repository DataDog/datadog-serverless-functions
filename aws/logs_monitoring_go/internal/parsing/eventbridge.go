// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"

	"github.com/aws/aws-lambda-go/events"
)

type s3EventBridgeDetail struct {
	Bucket struct {
		Name string `json:"name"`
	} `json:"bucket"`
	Object struct {
		Key string `json:"key"`
	} `json:"object"`
}

func eventBridge(event json.RawMessage) (Event, error) {
	var eventBridgeEvent events.EventBridgeEvent
	if err := json.Unmarshal(event, &eventBridgeEvent); err != nil {
		return Event{}, fmt.Errorf("unmarshal: %w", err)
	}

	if eventBridgeEvent.Source == "aws.s3" && strings.Contains(eventBridgeEvent.DetailType, "Object Created") {
		var s3eb s3EventBridgeDetail
		if err := json.Unmarshal(eventBridgeEvent.Detail, &s3eb); err != nil {
			return Event{}, fmt.Errorf("unmarshal: %w", err)
		}

		payload, err := mapS3EventBridge(s3eb)
		if err != nil {
			return Event{}, err
		}

		slog.Debug("S3 notification found in EventBridge")
		return Event{ContentType: ContentTypeS3, Payload: payload}, nil
	}
	return Event{ContentType: ContentTypeEventBridge, Payload: event}, nil
}

func mapS3EventBridge(eb s3EventBridgeDetail) (json.RawMessage, error) {
	s3EventRecord := events.S3EventRecord{
		EventSource: eventSourceS3,
		S3: events.S3Entity{
			Bucket: events.S3Bucket{Name: eb.Bucket.Name},
			Object: events.S3Object{Key: eb.Object.Key, URLDecodedKey: eb.Object.Key},
		},
	}
	payload, err := json.Marshal(s3EventRecord)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}

	return payload, nil
}
