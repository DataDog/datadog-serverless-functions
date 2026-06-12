// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

type invalidAPIKeyError struct {
	message string
}

func (e invalidAPIKeyError) Error() string {
	return "invalid Datadog API key: " + e.message + ". See https://docs.datadoghq.com/serverless/forwarder/ for more information."
}
