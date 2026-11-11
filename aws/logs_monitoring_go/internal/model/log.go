// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

const (
	sourceCategory = "aws"

	TagsJSONKey = "ddtags"
)

type Source string

type LogEntry struct {
	Host           string    `json:"host,omitzero"`
	ID             string    `json:"id,omitzero"`
	Timestamp      int64     `json:"timestamp,omitzero"`
	Message        string    `json:"message,omitzero"`
	Service        string    `json:"service,omitzero"`
	Source         Source    `json:"ddsource"`
	SourceCategory string    `json:"ddsourcecategory"`
	Tags           Tags      `json:"ddtags"`
	Metadata       any       `json:"aws"`
	Lambda         LambdaLog `json:"lambda,omitzero"`
}

func NewLogEntry() LogEntry {
	return LogEntry{
		SourceCategory: sourceCategory,
	}
}
