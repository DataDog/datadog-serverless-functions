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
	NoSSL             bool
	SkipSSLValidation bool
	LogLevel          string
	UseFIPS           bool
}

func Load(ctx context.Context) (*Config, error) {
	cfg := &Config{
		Site:              envOrDefault("DD_SITE", "datadoghq.com"),
		Port:              envOrDefaultInt("DD_PORT", 443),
		NoSSL:             envOrDefaultBool("DD_NO_SSL", false),
		SkipSSLValidation: envOrDefaultBool("DD_SKIP_SSL_VALIDATION", false),
		LogLevel:          envOrDefault("DD_LOG_LEVEL", "INFO"),
		UseFIPS:           envOrDefaultBool("DD_USE_FIPS", false),
	}

	cfg.deriveURLs()

	logDroppedEnvVars()

	if err := cfg.resolveAPIKey(ctx); err != nil {
		return nil, fmt.Errorf("resolving API key: %w", err)
	}

	if err := cfg.validateAPIKey(); err != nil {
		return nil, fmt.Errorf("validating API key: %w", err)
	}

	return cfg, nil
}

func (c *Config) deriveURLs() {
	scheme := "https"
	if c.NoSSL {
		scheme = "http"
	}
	c.URL = envOrDefault("DD_URL", "http-intake.logs."+c.Site)
	c.APIURL = envOrDefault("DD_API_URL", fmt.Sprintf("%s://api.%s", scheme, c.Site))
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

func logDroppedEnvVars() {
	for _, name := range deprecatedEnvironmentVariables {
		if _, ok := os.LookupEnv(name); ok {
			slog.Warn("deprecated env var set, will be ignored", "name", name)
		}
	}
}
