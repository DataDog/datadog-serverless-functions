// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

type CloudwatchLogsContext struct {
	LogGroup  string `json:"logGroup"`
	LogStream string `json:"logStream"`
	Owner     string `json:"owner"`
}

func (CloudwatchLogsContext) InvocationKey() string { return "awslogs" }

type CloudwatchLogsContent struct {
	ID        string `json:"id"`
	Timestamp int64  `json:"timestamp"`
	Msg       string `json:"message"`
}

func (c CloudwatchLogsContent) Message() string {
	return c.Msg
}

func (c CloudwatchLogsContent) MarshalFields() (map[string]any, error) {
	return map[string]any{
		"id":        c.ID,
		"timestamp": c.Timestamp,
		"message":   c.Msg,
	}, nil
}
