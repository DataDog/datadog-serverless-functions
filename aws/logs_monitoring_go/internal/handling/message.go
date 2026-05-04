// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"encoding/json"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

func extractFromMessage(message string) (model.Tags, string, string) {
	var tags model.Tags
	var service string
	var jsonMessage map[string]any
	if err := json.Unmarshal([]byte(message), &jsonMessage); err != nil {
		return nil, service, message
	}

	ddtagsRaw, ok := jsonMessage[config.DdtagsJSONKey]
	if !ok {
		return nil, service, message
	}

	ddtagsStr, ok := ddtagsRaw.(string)
	if !ok {
		return nil, service, message
	}

	ddtagsStr = strings.ReplaceAll(ddtagsStr, " ", "")
	for tag := range strings.SplitSeq(ddtagsStr, config.TagSeparator) {
		if tag == "" {
			continue
		}
		v, found := strings.CutPrefix(tag, config.ServiceKey)
		if found {
			if service == "" {
				service = v
			}
			continue
		}
		tags = append(tags, tag)
	}

	delete(jsonMessage, config.DdtagsJSONKey)

	newMessage, err := json.Marshal(jsonMessage)
	if err != nil {
		return nil, service, message
	}

	return tags, service, string(newMessage)
}
