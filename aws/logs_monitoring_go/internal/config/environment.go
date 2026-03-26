// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"log/slog"
	"os"
	"strings"
)

var deprecatedEnvironmentVariables = []string{
	"DD_ADDITIONAL_TARGET_LAMBDAS",
	"DD_API_KEY",
	"DD_COMPRESSION_LEVEL",
	"DD_ENRICH_CLOUDWATCH_TAGS",
	"DD_ENRICH_S3_TAGS",
	"DD_FETCH_LAMBDA_TAGS",
	"DD_FETCH_LOG_GROUP_TAGS",
	"DD_FETCH_S3_TAGS",
	"DD_FETCH_STEP_FUNCTIONS_TAGS",
	"DD_FORWARD_LOG",
	"DD_NO_SSL",
	"DD_PORT",
	"DD_SKIP_SSL_VALIDATION",
	"DD_TAGS_CACHE_TTL_SECONDS",
	"DD_TRACE_INTAKE_URL",
	"DD_USE_COMPRESSION",
	"DD_USE_VPC",
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
	return strings.EqualFold(v, "true")
}

func logDroppedEnvVars() {
	for _, name := range deprecatedEnvironmentVariables {
		if _, ok := os.LookupEnv(name); ok {
			slog.Warn("deprecated env var set, will be ignored", slog.String("name", name))
		}
	}
}
