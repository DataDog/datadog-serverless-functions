// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

type CloudwatchLogEntry struct {
	ID             string             `json:"id"`
	Timestamp      int64              `json:"timestamp"`
	Message        string             `json:"message"`
	Source         string             `json:"ddsource"`
	SourceCategory string             `json:"ddsourcecategory"`
	Service        string             `json:"service"`
	Host           string             `json:"hostname"`
	Tags           Tags               `json:"ddtags"`
	AWS            CloudwatchMetadata `json:"aws"`
}

type CloudwatchMetadata struct {
	ForwarderMetadata
	Logs CloudwatchLogsContext `json:"awslogs"`
}

type CloudwatchLogsContext struct {
	LogGroup  string `json:"logGroup"`
	LogStream string `json:"logStream"`
	Owner     string `json:"owner"`
}
