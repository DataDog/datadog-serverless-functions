// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bytes"
	"encoding/json"
)

//go:generate stringer -type InvocationSource -trimprefix InvocationSource -output invocation_source_string.go
type InvocationSource int

const (
	InvocationSourceUnknown InvocationSource = iota
	InvocationSourceCloudwatchLogs
	InvocationSourceS3
	InvocationSourceSNS
	InvocationSourceSQS
	InvocationSourceKinesis
)

func DetectInvocationSource(event json.RawMessage) InvocationSource {
	dec := json.NewDecoder(bytes.NewReader(event))

	t, err := dec.Token()
	if err != nil || t != json.Delim('{') {
		return InvocationSourceUnknown
	}

	key, err := dec.Token()
	if err != nil {
		return InvocationSourceUnknown
	}
	if key == "awslogs" {
		return InvocationSourceCloudwatchLogs
	}

	if key == "Records" {
		return detectFromRecords(dec)
	}

	return InvocationSourceUnknown
}

func detectFromRecords(dec *json.Decoder) InvocationSource {
	t, err := dec.Token()
	if err != nil || t != json.Delim('[') {
		return InvocationSourceUnknown
	}

	t, err = dec.Token()
	if err != nil || t != json.Delim('{') {
		return InvocationSourceUnknown
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return InvocationSourceUnknown
		}
		if key == "eventSource" {
			val, err := dec.Token()
			if err != nil {
				return InvocationSourceUnknown
			}
			switch val {
			case "aws:s3":
				return InvocationSourceS3
			case "aws:sns":
				return InvocationSourceSNS
			case "aws:sqs":
				return InvocationSourceSQS
			case "aws:kinesis":
				return InvocationSourceKinesis
			default:
				return InvocationSourceUnknown
			}
		}
		var skip json.RawMessage
		if err := dec.Decode(&skip); err != nil {
			return InvocationSourceUnknown
		}
	}

	return InvocationSourceUnknown
}
