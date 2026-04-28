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
	var filter Filter
	var err error
	if includeMatch != "" {
		re, includeErr := regexp.Compile(includeMatch)
		if includeErr != nil {
			err = errors.Join(err, fmt.Errorf("compile custom include: %w", includeErr))
		} else {
			filter.includeRegex = re
		}
	}
	if excludeMatch != "" {
		re, excludeErr := regexp.Compile(excludeMatch)
		if excludeErr != nil {
			err = errors.Join(err, fmt.Errorf("compile custom exclude: %w", excludeErr))
		} else {
			filter.excludeRegex = re
		}
	}
	if err != nil {
		return nil, err
	}
	return &filter, nil
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
