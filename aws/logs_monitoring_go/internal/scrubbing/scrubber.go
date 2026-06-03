// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package scrubbing

import (
	"regexp"
)

type scrubbingRule struct {
	regex       *regexp.Regexp
	replacement string
}

var ipRule = scrubbingRule{
	regex:       regexp.MustCompile(`\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}`),
	replacement: "xxx.xxx.xxx.xxx",
}

var emailRule = scrubbingRule{
	regex:       regexp.MustCompile(`[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+`),
	replacement: "xxxxx@xxxxx.com",
}

type Scrubber struct {
	rules []scrubbingRule
}

func NewScrubber(customMatch *regexp.Regexp, customReplacement string, ip, email bool) *Scrubber {
	var rules []scrubbingRule

	if ip {
		rules = append(rules, ipRule)
	}
	if email {
		rules = append(rules, emailRule)
	}

	if customMatch != nil {
		rules = append(rules, scrubbingRule{
			regex:       customMatch,
			replacement: customReplacement,
		})
	}

	return &Scrubber{rules: rules}
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
