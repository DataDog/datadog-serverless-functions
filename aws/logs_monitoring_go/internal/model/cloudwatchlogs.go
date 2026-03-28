// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

// CloudwatchLogsContext holds transport metadata for CloudWatch Logs events.
type CloudwatchLogsContext struct {
	LogGroup  string `json:"logGroup"`
	LogStream string `json:"logStream"`
	Owner     string `json:"owner"`
}

// InvocationKey returns the JSON key used under the "aws" object.
func (CloudwatchLogsContext) InvocationKey() string { return "awslogs" }

// CloudwatchLogsContent holds the log data from a CloudWatch Logs event.
type CloudwatchLogsContent struct {
	ID        string `json:"id"`
	Timestamp int64  `json:"timestamp"`
	Msg       string `json:"message"`
}

// Message returns the log message text.
func (c CloudwatchLogsContent) Message() string {
	return c.Msg
}

// MarshalFields returns the specific top-level JSON fields.
func (c CloudwatchLogsContent) MarshalFields() (map[string]any, error) {
	return map[string]any{
		"id":        c.ID,
		"timestamp": c.Timestamp,
		"message":   c.Msg,
	}, nil
}
