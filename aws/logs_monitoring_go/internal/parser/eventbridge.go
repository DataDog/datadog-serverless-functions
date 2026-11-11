// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parser

import (
	"encoding/json/jsontext"
	"encoding/json/v2"
	"fmt"
	"log/slog"
	"net/url"
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

func eventBridge(event jsontext.Value) (Event, error) {
	var e events.EventBridgeEvent
	if err := json.Unmarshal(event, &e); err != nil {
		return Event{}, fmt.Errorf("unmarshal: %w", err)
	}

	if e.Source == "aws.s3" && strings.Contains(e.DetailType, "Object Created") {
		var d s3EventBridgeDetail
		if err := json.Unmarshal(e.Detail, &d); err != nil {
			return Event{}, fmt.Errorf("unmarshal: %w", err)
		}

		payload, err := toS3(d.Bucket.Name, d.Object.Key)
		if err != nil {
			return Event{}, err
		}

		slog.Debug("S3 notification found in EventBridge")
		return Event{ContentType: ContentTypeS3, Payload: payload}, nil
	}
	return Event{ContentType: ContentTypeEventBridge, Payload: event}, nil
}

func toS3(bucket, key string) (jsontext.Value, error) {
	s3Event := events.S3Event{
		Records: []events.S3EventRecord{{
			EventSource: eventSourceS3,
			S3: events.S3Entity{
				Bucket: events.S3Bucket{Name: bucket},
				Object: events.S3Object{Key: url.QueryEscape(key)},
			},
		}},
	}
	payload, err := json.Marshal(s3Event)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}

	return payload, nil
}
