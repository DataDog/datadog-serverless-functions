// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package filtering

import (
	"errors"
	"fmt"
	"regexp"
)

type Filter struct {
	includeRegex *regexp.Regexp
	excludeRegex *regexp.Regexp
}

func NewFilter(includeMatch, excludeMatch string) (*Filter, error) {
	includeRegex, includeErr := compilePattern(includeMatch)
	excludeRegex, excludeErr := compilePattern(excludeMatch)

	if err := errors.Join(includeErr, excludeErr); err != nil {
		return nil, err
	}
	return &Filter{includeRegex: includeRegex, excludeRegex: excludeRegex}, nil
}

func compilePattern(pattern string) (*regexp.Regexp, error) {
	if pattern == "" {
		return nil, nil
	}

	re, err := regexp.Compile(pattern)
	if err != nil {
		return nil, fmt.Errorf("compile '%s': %w", pattern, err)
	}
	return re, nil
}

func (f *Filter) ShouldExclude(content string) bool {
	if f == nil {
		return false
	}
	if f.excludeRegex != nil && f.excludeRegex.MatchString(content) {
		return true
	}
	if f.includeRegex != nil && !f.includeRegex.MatchString(content) {
		return true
	}
	return false
}
