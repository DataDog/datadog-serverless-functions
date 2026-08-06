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
	if !strings.Contains(message, "ddtags") {
		return nil, "", message
	}

	var fields map[string]json.RawMessage
	if err := json.Unmarshal([]byte(message), &fields); err != nil {
		return nil, "", message
	}

	ddtagsRaw, ok := fields[config.DdtagsJSONKey]
	if !ok {
		return nil, "", message
	}

	var ddtagsStr string
	if err := json.Unmarshal(ddtagsRaw, &ddtagsStr); err != nil {
		return nil, "", message
	}

	ddtagsStr = strings.ReplaceAll(ddtagsStr, " ", "")

	var tags model.Tags
	var service string
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

	delete(fields, config.DdtagsJSONKey)

	newMessage, err := json.Marshal(fields)
	if err != nil {
		return nil, "", message
	}

	return tags, service, string(newMessage)
}
