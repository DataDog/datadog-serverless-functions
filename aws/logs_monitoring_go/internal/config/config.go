// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"strconv"
	"strings"
)

var deprecatedEnvironmentVariables = []string{
	"DD_ADDITIONAL_TARGET_LAMBDAS",
	"DD_ENRICH_CLOUDWATCH_TAGS",
	"DD_ENRICH_S3_TAGS",
	"DD_FETCH_LAMBDA_TAGS",
	"DD_FETCH_LOG_GROUP_TAGS",
	"DD_FETCH_S3_TAGS",
	"DD_FETCH_STEP_FUNCTIONS_TAGS",
	"DD_TAGS_CACHE_TTL_SECONDS",
	"DD_TRACE_INTAKE_URL",
	"DD_USE_VPC",
}

type Config struct {
	APIKey            string
	Site              string
	URL               string
	Port              int
	APIURL            string
	ForwardLog        bool
	UseCompression    bool
	CompressionLevel  int
	NoSSL             bool
	SkipSSLValidation bool
	Tags              string
	Source            string
	LogLevel          string
	UseFIPS           bool
}

func Load(ctx context.Context) (*Config, error) {
	cfg := &Config{
		Site:              envOrDefault("DD_SITE", "datadoghq.com"),
		Port:              envOrDefaultInt("DD_PORT", 443),
		ForwardLog:        envOrDefaultBool("DD_FORWARD_LOG", true),
		UseCompression:    envOrDefaultBool("DD_USE_COMPRESSION", true),
		CompressionLevel:  envOrDefaultInt("DD_COMPRESSION_LEVEL", 6),
		NoSSL:             envOrDefaultBool("DD_NO_SSL", false),
		SkipSSLValidation: envOrDefaultBool("DD_SKIP_SSL_VALIDATION", false),
		Tags:              envOrDefault("DD_TAGS", ""),
		Source:            envOrDefault("DD_SOURCE", ""),
		LogLevel:          envOrDefault("DD_LOG_LEVEL", "INFO"),
	}

	scheme := "https"
	if cfg.NoSSL {
		scheme = "http"
	}
	cfg.URL = envOrDefault("DD_URL", "http-intake.logs."+cfg.Site)
	cfg.APIURL = envOrDefault("DD_API_URL", fmt.Sprintf("%s://api.%s", scheme, cfg.Site))

	logDroppedEnvVars()

	useFIPS := envOrDefaultBool("DD_USE_FIPS", false)
	cfg.UseFIPS = useFIPS
	apiKey, err := resolveAPIKey(ctx, useFIPS)
	if err != nil {
		return nil, fmt.Errorf("resolving API key: %w", err)
	}
	cfg.APIKey = apiKey

	if err := validateAPIKey(cfg); err != nil {
		return nil, fmt.Errorf("validating API key: %w", err)
	}

	return cfg, nil
}

func logDroppedEnvVars() {
	for _, name := range deprecatedEnvironmentVariables {
		if _, ok := os.LookupEnv(name); ok {
			slog.Warn("deprecated env var set, will be ignored", "name", name)
		}
	}
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

func envOrDefaultInt(key string, fallback int) int {
	v, ok := os.LookupEnv(key)
	if !ok {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		slog.Warn("invalid integer for env var, using default", "key", key, "value", v, "default", fallback)
		return fallback
	}
	return n
}
