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

var deprecatedEnvironmentVariables = []string{
	"DD_ADDITIONAL_TARGET_LAMBDAS",
	"DD_API_KEY",
	"DD_ENRICH_CLOUDWATCH_TAGS",
	"DD_ENRICH_S3_TAGS",
	"DD_FETCH_LAMBDA_TAGS",
	"DD_FETCH_LOG_GROUP_TAGS",
	"DD_FETCH_S3_TAGS",
	"DD_FETCH_STEP_FUNCTIONS_TAGS",
	"DD_FORWARD_LOG",
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
	for _, name := range deprecatedEnvironmentVariables {
		if _, ok := os.LookupEnv(name); ok {
			slog.Warn("deprecated env var set, will be ignored", slog.String("name", name))
		}
	}
}
