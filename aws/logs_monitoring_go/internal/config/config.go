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

const (
	DefaultSite                = "datadoghq.com"
	DefaultLogLevel            = "INFO"
	EnvAPIKey                  = "DD_API_KEY"
	EnvSite                    = "DD_SITE"
	EnvURL                     = "DD_URL"
	EnvAPIURL                  = "DD_API_URL"
	EnvLogLevel                = "DD_LOG_LEVEL"
	EnvUseFIPS                 = "DD_USE_FIPS"
	EnvSource                  = "DD_SOURCE"
	EnvHost                    = "DD_HOST"
	EnvTags                    = "DD_TAGS"
	EnvMultilineLogRegex       = "DD_MULTILINE_LOG_REGEX_PATTERN"
	EnvScrubbingRule           = "DD_SCRUBBING_RULE"
	EnvScrubbingRuleReplcement = "DD_SCRUBBING_RULE_REPLACEMENT"
	EnvRedactIP                = "REDACT_IP"
	EnvRedactEmail             = "REDACT_EMAIL"
	EnvIncludeAtMatch          = "INCLUDE_AT_MATCH"
	EnvExcludeAtMatch          = "EXCLUDE_AT_MATCH"
	ForwarderVersion           = "6.0"
)

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
	logLevel := envOrDefault(EnvLogLevel, DefaultLogLevel)
	initLogger(logLevel)
	logDroppedEnvVars()

	var cfg Config
	cfg.LogLevel = logLevel
	cfg.loadEnv()
	cfg.extractFromEnv()

	err := cfg.compileS3MultilineLogRegex()

	scrubber, scrubbingErr := scrubbing.NewScrubber(
		envOrDefault(EnvScrubbingRule, ""),
		envOrDefault(EnvScrubbingRuleReplcement, ""),
		envOrDefaultBool(EnvRedactIP, false),
		envOrDefaultBool(EnvRedactEmail, false),
	)
	err = errors.Join(err, scrubbingErr)

	filter, filteringErr := filtering.NewFilter(
		envOrDefault(EnvIncludeAtMatch, ""),
		envOrDefault(EnvExcludeAtMatch, ""),
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
	c.Site = envOrDefault(EnvSite, DefaultSite)
	c.IntakeURL = envOrDefault(EnvURL, "https://http-intake.logs."+c.Site+"/api/v2/logs")
	c.APIURL = envOrDefault(EnvAPIURL, "https://api."+c.Site)
	c.UseFIPS = envOrDefaultBool(EnvUseFIPS, false)
	c.Source = envOrDefault(EnvSource, "")
	c.Host = envOrDefault(EnvHost, "")
}

func (c *Config) compileS3MultilineLogRegex() error {
	pattern := envOrDefault(EnvMultilineLogRegex, "")
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
