// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

type LogEntry struct {
	ID        string      `json:"id,omitempty"`
	Timestamp int64       `json:"timestamp,omitempty"`
	Message   string      `json:"message,omitempty"`
	Source    string      `json:"ddsource"`
	Service   string      `json:"service,omitempty"`
	Host      string      `json:"hostname,omitempty"`
	Tags      []string    `json:"ddtags"`
	AWS       AWSMetadata `json:"aws"`
}

type AWSMetadata struct {
	InvokedFunctionARN string                 `json:"invoked_function_arn"`
	FunctionVersion    string                 `json:"function_version,omitempty"`
	CloudwatchLogs     *CloudwatchLogsContext `json:"awslogs,omitempty"`
}
