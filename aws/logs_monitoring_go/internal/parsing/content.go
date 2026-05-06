// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import "encoding/json"

//go:generate stringer -type ContentType -trimprefix ContentType -output content_string.go
type ContentType int

const (
	ContentTypeUnknown ContentType = iota
	ContentTypeCloudwatchLogs
	ContentTypeS3
	ContentTypeKinesis
	ContentTypeEventBridge
)

type ParsedEvent struct {
	ContentType ContentType
	Payload     json.RawMessage
}
