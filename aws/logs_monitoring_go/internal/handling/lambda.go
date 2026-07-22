// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

func enrichLambdaLog(entry *model.LogEntry, forwarderARN, logGroup, logStream string) {
	name := lambdaName(strings.ToLower(logGroup), logStream)
	prefix, _, _ := strings.Cut(forwarderARN, "function:")

	arn := prefix + "function:" + name
	entry.Tags.Add("functionname", name)
	entry.Lambda = &model.LambdaLog{ARN: arn}
	entry.Host = arn
	entry.Service = name
}

func lambdaName(logGroup, logStream string) string {
	if m := lambdaLogStreamRegex.FindStringSubmatch(logStream); m != nil {
		return strings.ToLower(m[1])
	}

	if _, name, found := strings.Cut(logGroup, logGroupLambda+"/"); found && name != "" {
		return strings.ToLower(name)
	}
	return ""
}
