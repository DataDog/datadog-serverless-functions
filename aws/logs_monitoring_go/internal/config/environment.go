// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"log/slog"
	"os"
	"strconv"
)

var deprecatedEnvironmentVariables = []struct {
	name   string
	reason string
}{
	{"DD_API_KEY", "Plain text API keys are not supported for security reasons. Please use DD_API_KEY_SECRET_ARN, DD_API_KEY_SSM_NAME, or DD_KMS_API_KEY."},
	{"DD_ENRICH_CLOUDWATCH_TAGS", "Tag enrichment has moved to the Datadog backend. No configuration required."},
	{"DD_ENRICH_S3_TAGS", "Tag enrichment has moved to the Datadog backend. No configuration required."},
	{"DD_FETCH_LAMBDA_TAGS", "Tag enrichment has moved to the Datadog backend. No configuration required."},
	{"DD_FETCH_LOG_GROUP_TAGS", "Tag enrichment has moved to the Datadog backend. No configuration required."},
	{"DD_FETCH_S3_TAGS", "Tag enrichment has moved to the Datadog backend. No configuration required."},
	{"DD_FETCH_STEP_FUNCTIONS_TAGS", "Tag enrichment has moved to the Datadog backend. No configuration required."},
	{"DD_FORWARD_LOG", "This version only supports log forwarding. For metrics and traces, please use the Datadog Lambda Extension (https://docs.datadoghq.com/serverless/libraries_integrations/extension/)."},
	{"DD_HOST", "The host is derived from the log source and can no longer be overridden globally."},
	{"DD_STORE_FAILED_EVENTS", "Replaced by DD_S3_BUCKET_NAME or DD_SQS_QUEUE_URL."},
	{"DD_TAGS_CACHE_TTL_SECONDS", "Tag caching is no longer required. Tag enrichment has moved to the Datadog backend. No configuration required."},
	{"DD_TRACE_INTAKE_URL", "This version only supports log forwarding. For metrics and traces, please use the Datadog Lambda Extension (https://docs.datadoghq.com/serverless/libraries_integrations/extension/)."},
	{"DD_USE_COMPRESSION", "Set DD_COMPRESSION_LEVEL to 0 to disable compression."},
	{"DD_USE_VPC", "No longer required. S3 access through VPC endpoints works without additional configuration."},
}

func envOrDefault(key, fallback string) string {
	if v, ok := os.LookupEnv(key); ok {
		return v
	}

	return fallback
}

func envOrDefaultBool(key string, fallback bool) bool {
	v, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}

	b, err := strconv.ParseBool(v)
	if err != nil {
		slog.Warn("invalid boolean env var, using default", slog.String("key", key), slog.String("value", v), slog.Bool("default", fallback))
		return fallback
	}

	return b
}

func envOrDefaultInt(key string, fallback int) int {
	v, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}

	n, err := strconv.Atoi(v)
	if err != nil {
		slog.Warn("invalid integer env var, using default", slog.String("key", key), slog.String("value", v), slog.Int("default", fallback))
		return fallback
	}

	return n
}

func logDroppedEnvVars() {
	for _, d := range deprecatedEnvironmentVariables {
		if _, ok := os.LookupEnv(d.name); ok {
			slog.Warn("Deprecated environment variable usage, will be ignored.", slog.String("name", d.name), slog.String("reason", d.reason))
		}
	}
}
