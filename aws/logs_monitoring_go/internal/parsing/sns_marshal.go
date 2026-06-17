// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"

	"github.com/aws/aws-lambda-go/events"
)

func snsUnmarshal(event json.RawMessage) ([]Event, error) {
	var snsEvent events.SNSEvent
	if err := json.Unmarshal(event, &snsEvent); err != nil {
		return nil, err
	}

	var parsed []Event
	for _, record := range snsEvent.Records {
		inner := json.RawMessage(record.SNS.Message)

		var disc eventDiscriminator
		if err := json.Unmarshal(inner, &disc); err == nil && len(disc.Records) > 0 && disc.Records[0].EventSource == eventSourceS3 {
			parsed = append(parsed, Event{ContentType: ContentTypeS3, Payload: inner})
			continue
		}

		parsed = append(parsed, Event{ContentType: ContentTypeSNS, Payload: event})
	}

	return parsed, nil
}
