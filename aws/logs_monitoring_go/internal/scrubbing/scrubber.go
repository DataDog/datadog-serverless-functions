// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package scrubbing

import (
	"fmt"
	"regexp"
)

const (
	ipPattern    = `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}`
	emailPattern = `[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+`

	ipReplacement    = "xxx.xxx.xxx.xxx"
	emailReplacement = "xxxxx@xxxxx.com"
)

type scrubbingRule struct {
	regex       *regexp.Regexp
	replacement string
}

type Scrubber struct {
	rules []scrubbingRule
}

func NewScrubber(customMatch, customReplacement string, ip, email bool) (*Scrubber, error) {
	var rules []scrubbingRule
	if ip {
		rules = append(rules, scrubbingRule{
			regex:       regexp.MustCompile(ipPattern),
			replacement: ipReplacement,
		})
	}
	if email {
		rules = append(rules, scrubbingRule{
			regex:       regexp.MustCompile(emailPattern),
			replacement: emailReplacement,
		})
	}
	if customMatch != "" {
		re, err := regexp.Compile(customMatch)
		if err != nil {
			return nil, fmt.Errorf("compile custom scrubbing: %w", err)
		}

		rules = append(rules, scrubbingRule{
			regex:       re,
			replacement: customReplacement,
		})
	}
	return &Scrubber{rules: rules}, nil
}

func (s *Scrubber) Scrub(content string) string {
	if s == nil {
		return content
	}
	for _, rule := range s.rules {
		content = rule.regex.ReplaceAllString(content, rule.replacement)
	}
	return content
}
