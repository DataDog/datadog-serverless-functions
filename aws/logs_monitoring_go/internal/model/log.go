// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"encoding/json"
)

type LogEntry struct {
	Source  string
	Service string
	Host    string
	Tags    []string
	AWS     AWSMetadata
	Content LogContent
}

type AWSMetadata struct {
	InvokedFunctionARN string            `json:"invoked_function_arn"`
	FunctionVersion    string            `json:"function_version,omitempty"`
	Invocation         InvocationContext `json:"-"`
}

type LogContent interface {
	Message() string
	MarshalFields() (map[string]any, error)
}

type InvocationContext interface {
	InvocationKey() string
}

func (m AWSMetadata) MarshalJSON() ([]byte, error) {
	out := map[string]any{
		"invoked_function_arn": m.InvokedFunctionARN,
	}
	if m.FunctionVersion != "" {
		out["function_version"] = m.FunctionVersion
	}
	if m.Invocation != nil {
		out[m.Invocation.InvocationKey()] = m.Invocation
	}

	return json.Marshal(out)
}
