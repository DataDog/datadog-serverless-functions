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

func NewScrubber(cfg config.ScrubbingConfig) Scrubber {
	var rules []scrubbingRule

	if cfg.ScrubIP {
		rules = append(rules, scrubbingRule{
			regex:       regexp.MustCompile(ipPattern),
			replacement: ipReplacement,
		})
	}

	if cfg.ScrubEmail {
		rules = append(rules, scrubbingRule{
			regex:       regexp.MustCompile(emailPattern),
			replacement: emailReplacement,
		})
	}

	if cfg.CustomRule != "" {
		re, err := regexp.Compile(cfg.CustomRule)
		if err != nil {
			slog.Error("invalid custom scrubbing rule, make sure your regex is RE2 compatible",
				slog.String("pattern", cfg.CustomRule),
				slog.Any("error", err),
			)
		} else {
			rules = append(rules, scrubbingRule{
				regex:       re,
				replacement: cfg.CustomReplacement,
			})
		}
	}

	return Scrubber{rules: rules}
}

func (s Scrubber) ScrubMessage(msg string) string {
	for _, rule := range s.rules {
		msg = rule.regex.ReplaceAllString(msg, rule.replacement)
	}
	return msg
}
