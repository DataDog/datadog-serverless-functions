// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"

	"github.com/aws/aws-lambda-go/events"
)

type sqsBodyDiscriminator struct {
	Type    string          `json:"Type"`    // SNS inside SQS
	Message string          `json:"Message"` // SNS inside SQS
	Records json.RawMessage `json:"Records"` // S3 inside SQS
}

func sqsUnmarshal(event json.RawMessage) ([]ParsedEvent, error) {
	var sqsEvent events.SQSEvent
	if err := json.Unmarshal(event, &sqsEvent); err != nil {
		return nil, err
	}

	var parsed []ParsedEvent
	for _, msg := range sqsEvent.Records {
		pe, err := sqsBody(msg.Body)
		if err != nil {
			return nil, err
		}

		pe.SQSReceiptHandle = msg.ReceiptHandle
		parsed = append(parsed, pe)
	}

	return parsed, nil
}

func sqsBody(body string) (ParsedEvent, error) {
	raw := json.RawMessage(body)

	var disc sqsBodyDiscriminator
	if err := json.Unmarshal(raw, &disc); err != nil {
		return ParsedEvent{}, err
	}

	switch {
	case disc.Records != nil:
		return ParsedEvent{ContentType: ContentTypeS3, Payload: raw}, nil

	case disc.Type == "Notification" && disc.Message != "":
		var innerDisc recordsDiscriminator
		if err := json.Unmarshal([]byte(disc.Message), &innerDisc); err != nil {
			return ParsedEvent{ContentType: ContentTypeS3, Payload: json.RawMessage(disc.Message)}, nil
		}

		return ParsedEvent{ContentType: ContentTypeSNS, Payload: raw}, nil
	}

	return ParsedEvent{}, errUnknownEvent
}
