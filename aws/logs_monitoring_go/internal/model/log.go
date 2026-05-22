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
	Host           string `json:"host,omitempty"`
	ID             string `json:"id,omitempty"`
	Timestamp      int64  `json:"timestamp,omitempty"`
	Message        string `json:"message,omitempty"`
	Service        string `json:"service,omitempty"`
	Source         string `json:"ddsource"`
	SourceCategory string `json:"ddsourcecategory"`
	Tags           Tags   `json:"ddtags"`
	Metadata       any    `json:"aws"`
}

func NewLogEntry() LogEntry {
	return LogEntry{
		SourceCategory: sourceCategory,
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
