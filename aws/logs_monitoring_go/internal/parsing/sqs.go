// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"fmt"

	awsevents "github.com/aws/aws-lambda-go/events"
)

type SQSEvent struct {
	Event
	SQSReceiptHandle string
}

type sqsBodyDiscriminator struct {
	Type    string `json:"Type"`    // SNS inside SQS when raw message delivery disabled. See https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html
	Message string `json:"Message"` // SNS inside SQS when raw message delivery disabled. See https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html
	recordsDiscriminator
}

func IsSQS(event json.RawMessage) bool {
	var disc recordsDiscriminator
	if err := json.Unmarshal(event, &disc); err != nil {
		return false
	}
	return len(disc.Records) > 0 && disc.Records[0].EventSource == eventSourceSQS
}

func SQS(awsevent json.RawMessage) (events []SQSEvent, err error) {
	var sqsEvent awsevents.SQSEvent
	if err := json.Unmarshal(awsevent, &sqsEvent); err != nil {
		return nil, fmt.Errorf("unmarshal: %w", err)
	}

	for _, msg := range sqsEvent.Records {
		event, err := sqsBody(msg.Body)
		if err != nil {
			return nil, err
		}

		events = append(events, SQSEvent{Event: event, SQSReceiptHandle: msg.ReceiptHandle})
	}

	return events, nil
}

func sqsBody(body string) (Event, error) {
	raw := json.RawMessage(body)

	var disc sqsBodyDiscriminator
	if err := json.Unmarshal(raw, &disc); err != nil {
		return Event{}, fmt.Errorf("unmarshal: %w", err)
	}

	switch {
	case len(disc.Records) > 0 && disc.Records[0].EventSource == eventSourceS3:
		return Event{ContentType: ContentTypeS3, Payload: raw}, nil

	case disc.Type == "Notification" && disc.Message != "":
		var innerDisc recordsDiscriminator
		if err := json.Unmarshal([]byte(disc.Message), &innerDisc); err == nil && len(innerDisc.Records) > 0 && innerDisc.Records[0].EventSource == eventSourceS3 {
			return Event{ContentType: ContentTypeS3, Payload: json.RawMessage(disc.Message)}, nil
		}

		return Event{ContentType: ContentTypeSNS, Payload: raw}, nil
	}

	return Event{}, fmt.Errorf("unknown event")
}
