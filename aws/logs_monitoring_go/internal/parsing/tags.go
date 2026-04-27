// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/lambdacontext"
)

const (
	ddtagsJSONKey       = "ddtags"
	forwarderNameKey    = "forwardername:"
	forwarderVersionKey = "forwarder_version:"
	tagSeparator        = ","
	serviceKey          = "service:"
	sourceOverrideKey   = "source_overridden:"
)

func getTagsAndService(cfg *config.Config) (tags model.Tags, service string) {
	if cfg.CustomTags != "" {
		for tag := range strings.SplitSeq(cfg.CustomTags, tagSeparator) {
			v, found := strings.CutPrefix(tag, serviceKey)
			if found {
				if service == "" {
					service = v
				}
				continue
			}
			tags = append(tags, tag)
		}
	}

	if cfg.Source != "" {
		tags = append(tags, sourceOverrideKey+"true")
	}
	tags = append(tags,
		forwarderNameKey+strings.ToLower(lambdacontext.FunctionName),
		forwarderVersionKey+config.ForwarderVersion,
	)
	return
}

func extractFromMessage(message string) (model.Tags, string, string) {
	var tags model.Tags
	var service string
	var jsonMessage map[string]any
	if err := json.Unmarshal([]byte(message), &jsonMessage); err != nil {
		return nil, service, message
	}

	ddtagsRaw, ok := jsonMessage[ddtagsJSONKey]
	if !ok {
		return nil, service, message
	}

	ddtagsStr, ok := ddtagsRaw.(string)
	if !ok {
		return nil, service, message
	}

	ddtagsStr = strings.ReplaceAll(ddtagsStr, " ", "")
	for tag := range strings.SplitSeq(ddtagsStr, tagSeparator) {
		v, found := strings.CutPrefix(tag, serviceKey)
		if found {
			if service == "" {
				service = v
			}
			continue
		}
		tags = append(tags, tag)
	}

	delete(jsonMessage, ddtagsJSONKey)

	newMessage, err := json.Marshal(jsonMessage)
	if err != nil {
		return nil, service, message
	}

	return tags, service, string(newMessage)
}
