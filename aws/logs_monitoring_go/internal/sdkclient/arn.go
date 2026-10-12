// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

import "strings"

func regionFromARN(arn string) string {
	parts := strings.Split(arn, ":")
	if len(parts) < 6 || parts[0] != "arn" {
		return ""
	}

	return parts[3]
}
