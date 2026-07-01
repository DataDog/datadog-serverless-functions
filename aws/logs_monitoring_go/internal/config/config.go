// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"compress/gzip"
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"regexp"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

const (
	DefaultSite                 = "datadoghq.com"
	DefaultPort                 = "443"
	DefaultProtocol             = "https"
	DefaultLogLevel             = "INFO"
	EnvAPIKey                   = "DD_API_KEY"
	EnvSite                     = "DD_SITE"
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
	EnvSQSQueueURL              = "DD_SQS_QUEUE_URL"
	EnvStoreFailedEvents        = "DD_STORE_FAILED_EVENTS"
	EnvAdditionalTargets        = "DD_ADDITIONAL_TARGET_LAMBDAS"
	ForwarderVersion            = "6.0"
)

type apiKeyResolver struct {
	env     string
	resolve func(ctx context.Context, value string) (string, error)
}

var apiKeyResolvers = []apiKeyResolver{
	{"DD_API_KEY_SECRET_ARN", sdkclient.ResolveFromSecretsManager},
	{"DD_API_KEY_SSM_NAME", sdkclient.ResolveFromSSM},
	{"DD_KMS_API_KEY", sdkclient.ResolveFromKMS},
}

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
	SQSQueueURL           string
	AdditionalTargets     []string
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

	var resolutionErr error
	cfg.APIKey, resolutionErr = resolveAPIKey(context.Background(), apiKeyResolvers)
	errs = append(errs, resolutionErr)

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

	c.IntakeURL, c.APIURL = buildURLs(protocol, site, port)

	c.Source = envOrDefault(EnvSource, "")
	c.Host = envOrDefault(EnvHost, "")

	c.StoreOnFail = envOrDefaultBool(EnvStoreFailedEvents, false)
	c.S3RetryBucketName = envOrDefault(EnvS3RetryBucketName, "")
	c.SQSQueueURL = envOrDefault(EnvSQSQueueURL, "")

	c.ScrubbingReplacement = envOrDefault(EnvScrubbingRuleReplacement, "")
	c.ScrubIP = envOrDefaultBool(EnvRedactIP, false)
	c.ScrubEmail = envOrDefaultBool(EnvRedactEmail, false)

	if v := os.Getenv(EnvAdditionalTargets); v != "" {
		for target := range strings.SplitSeq(v, ",") {
			if target == "" {
				c.AdditionalTargets = append(c.AdditionalTargets, target)
			}
		}
	}
}

func buildURLs(protocol, site, port string) (intakeURL string, apiURL string) {
	intakeURL = protocol + "://http-intake.logs." + site + ":" + port + "/api/v2/logs"
	apiURL = protocol + "://api." + site + "/api/v1/validate"
	return
}

func resolveAPIKey(ctx context.Context, resolvers []apiKeyResolver) (string, error) {
	for _, resolver := range resolvers {
		v, ok := os.LookupEnv(resolver.env)
		if !ok {
			continue
		}

		key, err := resolver.resolve(ctx, v)
		if err != nil {
			return "", fmt.Errorf("resolve: %w", err)
		}

		return key, nil
	}

	return "", errors.New("no Datadog API key configured")
}
