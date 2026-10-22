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
	"os"
	"regexp"
	"strconv"
	"strings"
)

const (
	DefaultSite     = "datadoghq.com"
	DefaultPort     = "443"
	DefaultProtocol = "https"
)

const (
	EnvAPIKey                   = "DD_API_KEY"
	EnvSite                     = "DD_SITE"
	EnvLogLevel                 = "DD_LOG_LEVEL"
	EnvPort                     = "DD_PORT"
	EnvUseHTTP                  = "DD_NO_SSL"
	EnvSkipServerCertificate    = "DD_SKIP_SSL_VALIDATION"
	EnvIntakeURL                = "DD_URL"
	EnvAPIURL                   = "DD_API_URL"
	EnvCompressionLevel         = "DD_COMPRESSION_LEVEL"
	EnvSource                   = "DD_SOURCE"
	EnvTags                     = "DD_TAGS"
	EnvMultilineLogRegex        = "DD_MULTILINE_LOG_REGEX_PATTERN"
	EnvScrubbingRule            = "DD_SCRUBBING_RULE"
	EnvScrubbingRuleReplacement = "DD_SCRUBBING_RULE_REPLACEMENT"
	EnvRedactIP                 = "REDACT_IP"
	EnvRedactEmail              = "REDACT_EMAIL"
	EnvIncludeAtMatch           = "INCLUDE_AT_MATCH"
	EnvExcludeAtMatch           = "EXCLUDE_AT_MATCH"
	EnvStoreOnFail              = "DD_STORE_FAILED_EVENTS"
	EnvS3BucketName             = "DD_S3_BUCKET_NAME"
	EnvSQSQueueURL              = "DD_SQS_QUEUE_URL"
	EnvAdditionalTargets        = "DD_ADDITIONAL_TARGET_LAMBDAS"
	EnvEnableStepFunctionsTrace = "DD_STEP_FUNCTIONS_TRACE_ENABLED"
	EnvAPIKeySecretARN          = "DD_API_KEY_SECRET_ARN"
	EnvAPIKeySSMName            = "DD_API_KEY_SSM_NAME"
	EnvKMSAPIKey                = "DD_KMS_API_KEY"
)

type Config struct {
	APIKeySecretARN           string
	APIKeySSMName             string
	APIKeyKMSKey              string
	APIURL                    string
	IntakeURL                 string
	CompressionLevel          int
	SkipServerCertificate     bool
	Source                    string
	Tags                      string
	S3MultilineLogRegex       *regexp.Regexp
	FilterInclude             *regexp.Regexp
	FilterExclude             *regexp.Regexp
	ScrubbingRegex            *regexp.Regexp
	ScrubbingReplacement      string
	ScrubIP                   bool
	ScrubEmail                bool
	StoreOnFail               bool
	S3BucketName              string
	SQSQueueURL               string
	AdditionalTargets         []string
	StepFunctionsTraceEnabled bool
}

func Load() (Config, error) {
	var err error

	logDroppedEnvVars()

	site := envOrDefault(EnvSite, DefaultSite)
	port := envOrDefault(EnvPort, DefaultPort)
	protocol := DefaultProtocol
	if envOrDefaultBool(EnvUseHTTP, false) {
		protocol = "http"
	}
	intakeURL := envOrDefault(EnvIntakeURL, protocol+"://http-intake.logs."+site+":"+port+"/api/v2/logs")
	apiURL := envOrDefault(EnvAPIURL, protocol+"://api."+site+"/api/v1/validate")

	skipServerCertificate := envOrDefaultBool(EnvSkipServerCertificate, false)
	compressionLevel := getCompressionLevel(os.Getenv(EnvCompressionLevel))
	additionalTargets := getAdditionalTargets(os.Getenv(EnvAdditionalTargets))
	stepFunctionsTraceEnabled := envOrDefaultBool(EnvEnableStepFunctionsTrace, false)

	source := os.Getenv(EnvSource)

	scrubbingReplacement := envOrDefault(EnvScrubbingRuleReplacement, "")
	scrubIP := envOrDefaultBool(EnvRedactIP, false)
	scrubEmail := envOrDefaultBool(EnvRedactEmail, false)

	scrubbingRegex, scrubbingErr := compilePatternFromEnv(EnvScrubbingRule)
	filterInclude, includeErr := compilePatternFromEnv(EnvIncludeAtMatch)
	filterExclude, excludeErr := compilePatternFromEnv(EnvExcludeAtMatch)
	multilineRegex, multilineErr := compilePatternFromEnv(EnvMultilineLogRegex)
	err = errors.Join(err, scrubbingErr, includeErr, excludeErr, multilineErr)

	storeOnFail := envOrDefaultBool(EnvStoreOnFail, false)
	s3BucketName := os.Getenv(EnvS3BucketName)
	sqsQueueURL := os.Getenv(EnvSQSQueueURL)
	if storeOnFail && s3BucketName == "" && sqsQueueURL == "" {
		err = errors.Join(err, errors.New("failed event storage enabled, but no storage provided"))
	}

	return Config{
		APIKeySecretARN:           os.Getenv(EnvAPIKeySecretARN),
		APIKeySSMName:             os.Getenv(EnvAPIKeySSMName),
		APIKeyKMSKey:              os.Getenv(EnvKMSAPIKey),
		APIURL:                    apiURL,
		IntakeURL:                 intakeURL,
		CompressionLevel:          compressionLevel,
		SkipServerCertificate:     skipServerCertificate,
		Source:                    source,
		Tags:                      os.Getenv(EnvTags),
		S3MultilineLogRegex:       multilineRegex,
		FilterInclude:             filterInclude,
		FilterExclude:             filterExclude,
		ScrubbingRegex:            scrubbingRegex,
		ScrubbingReplacement:      scrubbingReplacement,
		ScrubIP:                   scrubIP,
		ScrubEmail:                scrubEmail,
		StoreOnFail:               storeOnFail,
		S3BucketName:              s3BucketName,
		SQSQueueURL:               sqsQueueURL,
		AdditionalTargets:         additionalTargets,
		StepFunctionsTraceEnabled: stepFunctionsTraceEnabled,
	}, err
}

func compilePatternFromEnv(env string) (*regexp.Regexp, error) {
	pattern := strings.TrimSpace(os.Getenv(env))
	if pattern == "" {
		return nil, nil
	}

	re, err := regexp.Compile(pattern)
	if err != nil {
		return nil, fmt.Errorf("compile %s %q: %w", env, pattern, err)
	}

	return re, nil
}

func getAdditionalTargets(targets string) []string {
	var additionalTargets []string
	for target := range strings.SplitSeq(targets, ",") {
		if strings.TrimSpace(target) != "" {
			additionalTargets = append(additionalTargets, target)
		}
	}
	return additionalTargets
}

func getCompressionLevel(level string) int {
	if level == "" {
		return gzip.DefaultCompression
	}

	v, err := strconv.Atoi(level)
	if err != nil {
		slog.Warn("invalid compression level, using default", slog.String("level", level))
		return gzip.DefaultCompression
	}

	if gzip.HuffmanOnly <= v && v <= gzip.BestCompression {
		return v
	}

	slog.Warn("invalid compression level, falling back to default", slog.String("level", level))
	return gzip.DefaultCompression
}

func (c Config) LogValue() slog.Value {
	return slog.GroupValue(
		slog.Bool("api_key_configured", c.APIKeySecretARN != "" || c.APIKeySSMName != "" || c.APIKeyKMSKey != ""),
		slog.String("api_url", c.APIURL),
		slog.String("intake_url", c.IntakeURL),
		slog.Int("compression_level", c.CompressionLevel),
		slog.Bool("skip_tls", c.SkipServerCertificate),
		slog.Bool("store_on_fail", c.StoreOnFail),
		slog.String("s3_bucket", c.S3BucketName),
		slog.String("sqs_queue_url", c.SQSQueueURL),
		slog.String("source_override", c.Source),
		slog.String("tags", c.Tags),
		slog.Bool("multiline_regex", c.S3MultilineLogRegex != nil),
		slog.Bool("filter_include", c.FilterInclude != nil),
		slog.Bool("filter_exclude", c.FilterExclude != nil),
		slog.Bool("scrub_ip", c.ScrubIP),
		slog.Bool("scrub_email", c.ScrubEmail),
		slog.Bool("scrub_custom", c.ScrubbingRegex != nil),
		slog.Any("additional_targets", c.AdditionalTargets),
		slog.Bool("step_functions_trace_enabled", c.StepFunctionsTraceEnabled),
	)
}
