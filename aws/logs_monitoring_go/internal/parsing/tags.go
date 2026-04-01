// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/aws/aws-lambda-go/lambdacontext"
)

func getTagsAndService(cfg config.Config) ([]string, string) {
	var tags []string
	var service string

	if cfg.CustomTags != "" {
		for _, tag := range strings.Split(cfg.CustomTags, ",") {
			if strings.HasPrefix(tag, "service:") {
				if service != "" {
					continue
				}
				service = tag[8:]
			}

			tags = append(tags, tag)
		}
	}

	if cfg.Source != "" {
		tags = append(tags, "source_overridden:true")
	}

	tags = append(tags,
		"forwardername:"+strings.ToLower(lambdacontext.FunctionName),
		"forwarder_version:"+config.ForwarderVersion,
	)

	return tags, service
}
