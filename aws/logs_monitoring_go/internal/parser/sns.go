// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parser

import (
	"encoding/json/jsontext"
	"encoding/json/v2"
	"fmt"

	"github.com/aws/aws-lambda-go/events"
)

func sns(event jsontext.Value) (Event, error) {
	var e events.SNSEvent
	if err := json.Unmarshal(event, &e); err != nil {
		return Event{}, fmt.Errorf("unmarshal: %w", err)
	}

	msg := jsontext.Value(e.Records[0].SNS.Message)

	var disc recordsDiscriminator
	if err := json.Unmarshal(msg, &disc); err == nil && len(disc.Records) > 0 && disc.Records[0].EventSource == eventSourceS3 {
		return Event{ContentType: ContentTypeS3, Payload: msg}, nil
	}

	return Event{ContentType: ContentTypeSNS, Payload: msg}, nil
}
