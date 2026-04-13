// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package processing

import (
	"log/slog"
	"regexp"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
)

type Filter struct {
	includeRegex *regexp.Regexp
	excludeRegex *regexp.Regexp
}

func NewFilter(cfg config.FilteringConfig) Filter {
	var f Filter

	if cfg.IncludePattern != "" {
		re, err := regexp.Compile(cfg.IncludePattern)
		if err != nil {
			slog.Error("invalid include filter pattern", slog.String("pattern", cfg.IncludePattern), slog.Any("error", err))
		} else {
			f.includeRegex = re
		}
	}

	if cfg.ExcludePattern != "" {
		re, err := regexp.Compile(cfg.ExcludePattern)
		if err != nil {
			slog.Error("invalid exclude filter pattern", slog.String("pattern", cfg.ExcludePattern), slog.Any("error", err))
		} else {
			f.excludeRegex = re
		}
	}

	return f
}

func (f Filter) Match(msg string) bool {
	if f.excludeRegex != nil && f.excludeRegex.MatchString(msg) {
		return false
	}
	if f.includeRegex != nil && !f.includeRegex.MatchString(msg) {
		return false
	}
	return true
}
