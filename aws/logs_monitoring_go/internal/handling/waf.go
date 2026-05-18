// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import "encoding/json"

const (
	headersKey                     = "headers"
	nonTerminatingMatchingRulesKey = "nonTerminatingMatchingRules"
	ruleGroupListKey               = "ruleGroupList"
	ruleGroupIdKey                 = "ruleGroupId"
	ruleIDKey                      = "ruleId"
)

func flattenWAFMessage(message string) string {
	var msg map[string]any
	if err := json.Unmarshal([]byte(message), &msg); err != nil {
		return message
	}

	flattenHeaders(msg)
	flattenRuleGroupList(msg)
	flattenByKey(msg, "rateBasedRuleList", "rateBasedRuleName", "", false)
	flattenByKey(msg, nonTerminatingMatchingRulesKey, ruleIDKey, "", false)

	out, err := json.Marshal(msg)
	if err != nil {
		return message
	}
	return string(out)
}

func flattenByKey(src map[string]any, field, keyField, outputField string, alwaysWrite bool) {
	arr, ok := src[field].([]any)
	if !ok && !alwaysWrite {
		return
	}

	result := make(map[string]any, len(arr))
	for _, item := range arr {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}

		key, _ := obj[keyField].(string)
		if key == "" {
			continue
		}
		delete(obj, keyField)
		result[key] = obj
	}

	out := field
	if outputField != "" {
		delete(src, field)
		out = outputField
	}
	src[out] = result
}

func flattenHeaders(msg map[string]any) {
	httpReq, ok := msg["httpRequest"].(map[string]any)
	if !ok {
		return
	}
	headers, ok := httpReq[headersKey].([]any)
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
	httpReq[headersKey] = result
}

func flattenRuleGroupList(msg map[string]any) {
	arr, ok := msg[ruleGroupListKey].([]any)
	if !ok {
		return
	}

	result := make(map[string]any, len(arr))
	for _, item := range arr {
		group, ok := item.(map[string]any)
		if !ok {
			continue
		}

		groupID, _ := group[ruleGroupIdKey].(string)
		delete(group, ruleGroupIdKey)
		existing, ok := result[groupID].(map[string]any)
		if !ok {
			existing = make(map[string]any)
			result[groupID] = existing
		}

		flattenRuleGroupField(group, existing, "terminatingRule")
		flattenRuleGroupField(group, existing, nonTerminatingMatchingRulesKey)
		flattenRuleGroupField(group, existing, "excludedRules")
	}
	msg[ruleGroupListKey] = result
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
