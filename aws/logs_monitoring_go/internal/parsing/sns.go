// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"fmt"

	"github.com/aws/aws-lambda-go/events"
)

func sns(event json.RawMessage) ([]Event, error) {
	var snsEvent events.SNSEvent
	if err := json.Unmarshal(event, &snsEvent); err != nil {
		return nil, fmt.Errorf("unmarshal: %w", err)
	}

	var events []Event
	for _, record := range snsEvent.Records {
		inner := json.RawMessage(record.SNS.Message)

		var disc eventDiscriminator
		if err := json.Unmarshal(inner, &disc); err == nil && len(disc.Records) > 0 && disc.Records[0].EventSource == eventSourceS3 {
			events = append(events, Event{ContentType: ContentTypeS3, Payload: inner})
			continue
		}

		events = append(events, Event{ContentType: ContentTypeSNS, Payload: event})
	}

	return events, nil
}
