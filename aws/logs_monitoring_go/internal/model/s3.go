// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

type S3LogEntry struct {
	Message        string     `json:"message"`
	Source         string     `json:"ddsource"`
	SourceCategory string     `json:"ddsourcecategory"`
	Service        string     `json:"service"`
	Tags           Tags       `json:"ddtags"`
	Metadata       S3Metadata `json:"aws"`
}

type S3Metadata struct {
	Metadata
	S3Context S3Context `json:"s3"`
}

type S3Context struct {
	Bucket string `json:"bucket"`
	Key    string `json:"key"`
}
