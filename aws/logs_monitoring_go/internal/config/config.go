// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"errors"
	"fmt"
	"regexp"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
)

const ForwarderVersion = "6.0"

type Config struct {
	APIKey              string
	Site                string
	IntakeURL           string
	APIURL              string
	LogLevel            string
	UseFIPS             bool
	Source              string
	Host                string
	Tags                model.Tags
	Service             string
	Scrubber            *scrubbing.Scrubber
	Filter              *filtering.Filter
	S3MultilineLogRegex *regexp.Regexp
}

func Load() (*Config, error) {
	logLevel := envOrDefault("DD_LOG_LEVEL", "INFO")
	initLogger(logLevel)
	logDroppedEnvVars()

	var cfg Config
	cfg.LogLevel = logLevel
	cfg.loadEnv()
	cfg.extractFromEnv()

	err := cfg.compileS3MultilineLogRegex()

	scrubber, scrubbingErr := scrubbing.NewScrubber(
		envOrDefault("DD_SCRUBBING_RULE", ""),
		envOrDefault("DD_SCRUBBING_RULE_REPLACEMENT", ""),
		envOrDefaultBool("REDACT_IP", false),
		envOrDefaultBool("REDACT_EMAIL", false),
	)
	err = errors.Join(err, scrubbingErr)

	filter, filteringErr := filtering.NewFilter(
		envOrDefault("INCLUDE_AT_MATCH", ""),
		envOrDefault("EXCLUDE_AT_MATCH", ""),
	)
	err = errors.Join(err, filteringErr)
	if err != nil {
		return nil, err
	}

	cfg.Scrubber = scrubber
	cfg.Filter = filter
	return &cfg, nil
}

func (c *Config) loadEnv() {
	c.Site = envOrDefault("DD_SITE", "datadoghq.com")
	c.IntakeURL = envOrDefault("DD_URL", "https://http-intake.logs."+c.Site+"/api/v2/logs")
	c.APIURL = envOrDefault("DD_API_URL", "https://api."+c.Site)
	c.UseFIPS = envOrDefaultBool("DD_USE_FIPS", false)
	c.Source = envOrDefault("DD_SOURCE", "")
	c.Host = envOrDefault("DD_HOST", "")
}

func (c *Config) compileS3MultilineLogRegex() error {
	pattern := envOrDefault("DD_MULTILINE_LOG_REGEX_PATTERN", "")
	if pattern == "" {
		return nil
	}
	re, err := regexp.Compile(pattern)
	if err != nil {
		return fmt.Errorf("compile multiline log regex: %w", err)
	}
	c.S3MultilineLogRegex = re
	return nil
}

// if err := cfg.resolveAPIKey(ctx); err != nil {
// 	return nil, fmt.Errorf("resolving API key: %w", err)
// }
// if err := cfg.validateAPIKey(ctx); err != nil {
// 	return nil, fmt.Errorf("validating API key: %w", err)
// }
