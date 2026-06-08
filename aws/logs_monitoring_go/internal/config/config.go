// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"compress/gzip"
	"errors"
	"log/slog"
	"os"
	"regexp"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

const (
	DefaultSite     = "datadoghq.com"
	DefaultPort     = "443"
	DefaultProtocol = "https"
	DefaultLogLevel = "INFO"

	EnvAPIKey                   = "DD_API_KEY"
	EnvSite                     = "DD_SITE"
	EnvURL                      = "DD_URL"
	EnvAPIURL                   = "DD_API_URL"
	EnvLogLevel                 = "DD_LOG_LEVEL"
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
	EnvS3RetryBucketName        = "DD_S3_BUCKET_NAME"
	EnvStoreFailedEvents        = "DD_STORE_FAILED_EVENTS"
	ForwarderVersion            = "6.0"
)

type Config struct {
	APIKey                string
	APIURL                string
	IntakeURL             string
	CompressionLevel      int
	SkipServerCertificate bool
	Host                  string
	Source                string
	Service               string
	Tags                  model.Tags
	S3MultilineLogRegex   *regexp.Regexp
	FilterInclude         *regexp.Regexp
	FilterExclude         *regexp.Regexp
	ScrubbingRegex        *regexp.Regexp
	ScrubbingReplacement  string
	ScrubIP               bool
	ScrubEmail            bool
	StoreOnFail           bool
	S3RetryBucketName     string
}

func Load() (*Config, error) {
	initLogger(envOrDefault(EnvLogLevel, DefaultLogLevel))
	logDroppedEnvVars()

	var cfg Config
	cfg.loadEnv()
	cfg.extractFromEnv()

	var errs []error
	patterns := []struct {
		env   string
		field **regexp.Regexp
	}{
		{env: EnvScrubbingRule, field: &cfg.ScrubbingRegex},
		{env: EnvIncludeAtMatch, field: &cfg.FilterInclude},
		{env: EnvExcludeAtMatch, field: &cfg.FilterExclude},
		{env: EnvMultilineLogRegex, field: &cfg.S3MultilineLogRegex},
	}
	for _, pattern := range patterns {
		if envValue := os.Getenv(pattern.env); envValue != "" {
			re, err := regexp.Compile(envValue)
			*pattern.field = re
			errs = append(errs, err)
		}
	}

	return &cfg, errors.Join(errs...)
}

func (c *Config) loadEnv() {
	site := envOrDefault(EnvSite, DefaultSite)
	port := envOrDefault(EnvPort, DefaultPort)
	protocol := DefaultProtocol

	c.SkipServerCertificate = envOrDefaultBool(EnvSkipServerCertificate, false)

	if envOrDefaultBool(EnvUseHTTP, false) {
		protocol = "http"
	}

	compressionLevel := envOrDefaultInt(EnvCompressionLevel, gzip.DefaultCompression)
	if compressionLevel < gzip.HuffmanOnly || compressionLevel > gzip.BestCompression {
		slog.Warn("invalid compression level, falling back to default", slog.Int("level", compressionLevel), slog.Int("fallback", gzip.DefaultCompression))
		compressionLevel = gzip.DefaultCompression
	}
	c.CompressionLevel = compressionLevel

	c.IntakeURL = envOrDefault(EnvURL, protocol+"://http-intake.logs."+site+":"+port+"/api/v2/logs")
	c.APIURL = envOrDefault(EnvAPIURL, protocol+"://api."+site)

	c.Source = envOrDefault(EnvSource, "")
	c.Host = envOrDefault(EnvHost, "")

	c.StoreOnFail = envOrDefaultBool(EnvStoreFailedEvents, false)
	c.S3RetryBucketName = envOrDefault(EnvS3RetryBucketName, "")

	c.ScrubbingReplacement = envOrDefault(EnvScrubbingRuleReplacement, "")
	c.ScrubIP = envOrDefaultBool(EnvRedactIP, false)
	c.ScrubEmail = envOrDefaultBool(EnvRedactEmail, false)
}
