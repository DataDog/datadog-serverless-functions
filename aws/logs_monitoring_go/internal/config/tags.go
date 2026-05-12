// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"os"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/lambdacontext"
)

const (
	DdtagsJSONKey       = "ddtags"
	ServiceKey          = "service:"
	TagSeparator        = ","
	sourceOverrideKey   = "source_overridden:true"
	forwarderNameKey    = "forwardername:"
	forwarderVersionKey = "forwarder_version:"
)

func (c *Config) extractFromEnv() {
	var tags model.Tags

	if customTags := os.Getenv(EnvTags); customTags != "" {
		for tag := range strings.SplitSeq(customTags, TagSeparator) {
			v, found := strings.CutPrefix(tag, ServiceKey)
			if found {
				if c.Service == "" {
					c.Service = v
				}
				continue
			}
			tags = append(tags, tag)
		}
	}

	if c.Source != "" {
		tags = append(tags, sourceOverrideKey)
	}

	tags = append(tags,
		forwarderNameKey+strings.ToLower(lambdacontext.FunctionName),
		forwarderVersionKey+ForwarderVersion,
	)
	c.Tags = tags
}
