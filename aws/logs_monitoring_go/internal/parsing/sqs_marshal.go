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
	Type    string `json:"Type"`    // SNS inside SQS when raw message delivery disabled. See https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html
	Message string `json:"Message"` // SNS inside SQS when raw message delivery disabled. See https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html
	eventDiscriminator
}

func sqsUnmarshal(event json.RawMessage) ([]Event, error) {
	var sqsEvent events.SQSEvent
	if err := json.Unmarshal(event, &sqsEvent); err != nil {
		return nil, err
	}

	var parsed []Event
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

func sqsBody(body string) (Event, error) {
	raw := json.RawMessage(body)

	var disc sqsBodyDiscriminator
	if err := json.Unmarshal(raw, &disc); err != nil {
		return Event{}, err
	}

	switch {
	case len(disc.Records) > 0 && disc.Records[0].EventSource == eventSourceS3:
		return Event{ContentType: ContentTypeS3, Payload: raw}, nil

	case disc.Type == "Notification" && disc.Message != "":
		var innerDisc eventDiscriminator
		if err := json.Unmarshal([]byte(disc.Message), &innerDisc); err == nil && len(innerDisc.Records) > 0 && innerDisc.Records[0].EventSource == eventSourceS3 {
			return Event{ContentType: ContentTypeS3, Payload: json.RawMessage(disc.Message)}, nil
		}

		return Event{ContentType: ContentTypeSNS, Payload: raw}, nil
	}

	return Event{}, errUnknownEvent
}
