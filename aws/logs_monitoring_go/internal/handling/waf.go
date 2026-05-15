// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import "encoding/json"

const ruleIDKey = "ruleId"

func flattenWAFMessage(message string) string {
	var msg map[string]any
	if err := json.Unmarshal([]byte(message), &msg); err != nil {
		return message
	}

	flattenHeaders(msg)
	flattenRuleGroupList(msg)
	flattenByKey(msg, "rateBasedRuleList", "rateBasedRuleName")
	flattenByKey(msg, "nonTerminatingMatchingRules", ruleIDKey)

	out, err := json.Marshal(msg)
	if err != nil {
		return message
	}
	return string(out)
}

func flattenHeaders(msg map[string]any) {
	httpReq, ok := msg["httpRequest"].(map[string]any)
	if !ok {
		return
	}
	headers, ok := httpReq["headers"].([]any)
	if !ok {
		return
	}

	result := make(map[string]any, len(headers))
	for _, h := range headers {
		header, ok := h.(map[string]any)
		if !ok {
			continue
		}
		name, _ := header["name"].(string)
		if name == "" {
			continue
		}
		result[name] = header["value"]
	}
	httpReq["headers"] = result
}

func flattenByKey(msg map[string]any, field, keyField string) {
	arr, ok := msg[field].([]any)
	if !ok {
		return
	}

	result := make(map[string]any, len(arr))
	for _, item := range arr {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}
		key, _ := entry[keyField].(string)
		if key == "" {
			continue
		}
		delete(entry, keyField)
		result[key] = entry
	}
	msg[field] = result
}

func flattenRuleGroupList(msg map[string]any) {
	arr, ok := msg["ruleGroupList"].([]any)
	if !ok {
		return
	}

	result := make(map[string]any, len(arr))
	for _, item := range arr {
		group, ok := item.(map[string]any)
		if !ok {
			continue
		}
		groupID, _ := group["ruleGroupId"].(string)
		delete(group, "ruleGroupId")

		existing, ok := result[groupID].(map[string]any)
		if !ok {
			existing = make(map[string]any)
			result[groupID] = existing
		}

		flattenRuleGroupField(group, existing, "terminatingRule")
		flattenRuleGroupField(group, existing, "nonTerminatingMatchingRules")
		flattenRuleGroupField(group, existing, "excludedRules")
	}
	msg["ruleGroupList"] = result
}

func flattenRuleGroupField(group, dest map[string]any, field string) {
	val, exists := group[field]
	if !exists {
		return
	}

	target, ok := dest[field].(map[string]any)
	if !ok {
		target = make(map[string]any)
		dest[field] = target
	}

	switch v := val.(type) {
	case map[string]any: // terminatingRule
		id, _ := v[ruleIDKey].(string)
		delete(v, ruleIDKey)
		target[id] = v
	case []any: // nonTerminatingMatchingRules, excludedRules
		for _, item := range v {
			entry, ok := item.(map[string]any)
			if !ok {
				continue
			}
			id, _ := entry[ruleIDKey].(string)
			delete(entry, ruleIDKey)
			target[id] = entry
		}
	}
}
