// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"errors"
	"fmt"

	"github.com/aws/aws-lambda-go/events"
)

func sns(event json.RawMessage) (Event, error) {
	var snsEvent events.SNSEvent
	if err := json.Unmarshal(event, &snsEvent); err != nil {
		return Event{}, fmt.Errorf("unmarshal: %w", err)
	}

	inner := json.RawMessage(snsEvent.Records[0].SNS.Message)

	var disc recordsDiscriminator
	if err := json.Unmarshal(inner, &disc); err != nil {
		return Event{ContentType: ContentTypeSNS, Payload: inner}, nil
	}

	if len(disc.Records) > 0 && disc.Records[0].EventSource == eventSourceS3 {
		return Event{ContentType: ContentTypeS3, Payload: inner}, nil
	}

	return Event{}, errors.New("")
}
