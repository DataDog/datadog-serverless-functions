// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"compress/gzip"
	"errors"
	"fmt"
	"log/slog"
	"regexp"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
)

const (
	DefaultSite                 = "datadoghq.com"
	DefaultLogLevel             = "INFO"
	EnvAPIKey                   = "DD_API_KEY"
	EnvSite                     = "DD_SITE"
	EnvURL                      = "DD_URL"
	EnvAPIURL                   = "DD_API_URL"
	EnvLogLevel                 = "DD_LOG_LEVEL"
	EnvUseFIPS                  = "DD_USE_FIPS"
	EnvPort                     = "DD_PORT"
	EnvUseHTTP                  = "DD_NO_SSL"
	EnvSkipServerCertificate    = "DD_SKIP_SSL_VALIDATION"
	EnvCompressionLevel         = "DD_COMPRESSION_LEVEL"
	EnvSource                   = "DD_SOURCE"
	EnvHost                     = "DD_HOST"
	EnvTags                     = "DD_TAGS"
	EnvMultilineLogRegex        = "DD_MULTILINE_LOG_REGEX_PATTERN"
	EnvScrubbingRule            = "DD_SCRUBBING_RULE"
	EnvScrubbingRuleReplacement = "DD_SCRUBBING_RULE_REPLACEMENT"
	EnvRedactIP                 = "REDACT_IP"
	EnvRedactEmail              = "REDACT_EMAIL"
	EnvIncludeAtMatch           = "INCLUDE_AT_MATCH"
	EnvExcludeAtMatch           = "EXCLUDE_AT_MATCH"
	ForwarderVersion            = "6.0"
)

type Config struct {
	APIKey                string
	APIURL                string
	CompressionLevel      int
	Filter                *filtering.Filter
	Host                  string
	IntakeURL             string
	LogLevel              string
	Port                  string
	S3MultilineLogRegex   *regexp.Regexp
	Scrubber              *scrubbing.Scrubber
	Service               string
	Site                  string
	SkipServerCertificate bool
	Source                string
	Tags                  model.Tags
	UseFIPS               bool
	UseHTTP               bool
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
		envOrDefault(EnvScrubbingRuleReplacement, ""),
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
	c.SkipServerCertificate = envOrDefaultBool(EnvSkipServerCertificate, false)
	c.UseHTTP = envOrDefaultBool(EnvUseHTTP, false)

	scheme := "https"
	if c.UseHTTP {
		scheme = "http"
	}

	compressionLevel := envOrDefaultInt(EnvCompressionLevel, gzip.DefaultCompression)
	if compressionLevel < gzip.HuffmanOnly || compressionLevel > gzip.BestCompression {
		slog.Warn("invalid compression level, falling back to default", slog.Int("level", compressionLevel), slog.Int("fallback", gzip.DefaultCompression))
		compressionLevel = gzip.BestCompression
	}
	c.CompressionLevel = compressionLevel

	c.Port = envOrDefault(EnvPort, "443")
	c.IntakeURL = envOrDefault(EnvURL, scheme+"://http-intake.logs."+c.Site+":"+c.Port+"/api/v2/logs")
	c.APIURL = envOrDefault(EnvAPIURL, scheme+"://api."+c.Site)
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
