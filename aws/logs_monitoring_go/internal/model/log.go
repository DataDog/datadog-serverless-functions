// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

const sourceCategory = "aws"

type LogEntry struct {
	Host           string     `json:"host,omitempty"`
	ID             string     `json:"id,omitempty"`
	Timestamp      int64      `json:"timestamp,omitempty"`
	Message        string     `json:"message,omitempty"`
	Service        string     `json:"service,omitempty"`
	Source         string     `json:"ddsource"`
	SourceCategory string     `json:"ddsourcecategory"`
	Tags           Tags       `json:"ddtags"`
	Metadata       any        `json:"aws"`
	Lambda         *LambdaLog `json:"lambda,omitempty"`
}

func NewLogEntry() LogEntry {
	return LogEntry{
		SourceCategory: sourceCategory,
	}
}
