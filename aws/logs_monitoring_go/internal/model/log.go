// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"encoding/json"
	"strings"
)

const sourceCategory = "aws"

type LogEntry struct {
	Message        string `json:"message"`
	Source         string `json:"ddsource"`
	SourceCategory string `json:"ddsourcecategory"`
	Service        string `json:"service"`
	Tags           Tags   `json:"ddtags"`
	Metadata       any    `json:"aws"`
}

func NewLogEntry(metadata any, tags Tags, message, source, service string) LogEntry {
	return LogEntry{
		Message:        message,
		Source:         source,
		SourceCategory: sourceCategory,
		Service:        service,
		Tags:           tags,
		Metadata:       metadata,
	}
}

type Tags []string

func (t Tags) MarshalJSON() ([]byte, error) {
	return json.Marshal(strings.Join(t, ","))
}

func (t *Tags) UnmarshalJSON(data []byte) error {
	var s string

	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}
	if s == "" {
		*t = nil
		return nil
	}

	*t = strings.Split(s, ",")
	return nil
}
