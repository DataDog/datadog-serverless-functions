// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package filtering

import (
	"log/slog"
	"regexp"
)

type Filterer struct {
	includeRegex *regexp.Regexp
	excludeRegex *regexp.Regexp
}

// nit: we may not want to return a pointer here since there is no reason for the filterer to change
func NewFilterer(includeMatch, excludeMatch *regexp.Regexp) *Filterer {
	return &Filterer{includeRegex: includeMatch, excludeRegex: excludeMatch}
}

func (f *Filterer) ShouldExclude(content string) bool {
	if f == nil {
		return false
	}
	if f.excludeRegex != nil && f.excludeRegex.MatchString(content) {
		slog.Debug("exclude rule matched", slog.String("content", content))
		return true
	}
	if f.includeRegex != nil && !f.includeRegex.MatchString(content) {
		slog.Debug("include rule did not match, excluding", slog.String("content", content))
		return true
	}
	return false
}
