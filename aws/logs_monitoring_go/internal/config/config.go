// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"
	"fmt"
	"log/slog"
)

var ForwarderVersion = "dev"

type Config struct {
	APIKey     string
	Site       string
	IntakeURL  string
	APIURL     string
	LogLevel   string
	UseFIPS    bool
	Source     string
	Host       string
	CustomTags string
}

func Load(ctx context.Context) (*Config, error) {
	initLogger(envOrDefault("DD_LOG_LEVEL", "INFO"))
	logDroppedEnvVars()

	cfg := loadConfig()
	slog.Debug("config loaded", slog.String("site", cfg.Site), slog.String("intakeURL", cfg.IntakeURL), slog.String("apiURL", cfg.APIURL), slog.String("logLevel", cfg.LogLevel), slog.Bool("useFIPS", cfg.UseFIPS))

	if err := cfg.resolveAPIKey(ctx); err != nil {
		return nil, fmt.Errorf("resolving API key: %w", err)
	}

	if err := cfg.validateAPIKey(ctx); err != nil {
		return nil, fmt.Errorf("validating API key: %w", err)
	}

	return cfg, nil
}

func loadConfig() *Config {
	site := envOrDefault("DD_SITE", "datadoghq.com")
	return &Config{
		Site:       site,
		IntakeURL:  envOrDefault("DD_URL", "https://http-intake.logs."+site),
		APIURL:     envOrDefault("DD_API_URL", "https://api."+site),
		LogLevel:   envOrDefault("DD_LOG_LEVEL", "INFO"),
		UseFIPS:    envOrDefaultBool("DD_USE_FIPS", false),
		Source:     envOrDefault("DD_SOURCE", ""),
		Host:       envOrDefault("DD_HOST", ""),
		CustomTags: envOrDefault("DD_TAGS", ""),
	}
}
