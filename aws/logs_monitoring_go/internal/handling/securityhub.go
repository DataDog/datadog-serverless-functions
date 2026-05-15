// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import "encoding/json"

const (
	findingKey  = "finding"
	findingsKey = "findings"
)

func separateFindings(event json.RawMessage) ([]string, bool) {
	var raw map[string]any
	if err := json.Unmarshal(event, &raw); err != nil {
		return nil, false
	}

	detail, _ := raw["detail"].(map[string]any)
	findings, _ := detail[findingsKey].([]any)
	if len(findings) == 0 {
		return nil, false
	}

	delete(detail, findingsKey)

	messages := make([]string, 0, len(findings))
	for _, f := range findings {
		finding, ok := f.(map[string]any)
		if !ok {
			continue
		}
		flattenByKey(finding, "Resources", "Type", "resources", true)
		detail[findingKey] = finding

		out, err := json.Marshal(raw)
		if err != nil {
			continue
		}
		messages = append(messages, string(out))
	}
	return messages, true
}
