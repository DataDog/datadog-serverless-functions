// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import "github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"

const (
	cloudwatchStorage = "cloudwatch"
	s3Storage         = "s3"
)

func Storage(source parsing.InvocationSource) string {
	switch source {
	case parsing.InvocationSourceS3:
		return s3Storage
	case parsing.InvocationSourceCloudwatchLogs, parsing.InvocationSourceKinesis:
		return cloudwatchStorage
	default:
		return ""
	}
}
