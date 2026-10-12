// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

import (
	"encoding/json"
	"strings"
)

const (
	KeyValueSeparator = ":"
	TagSeparator      = ","
)

const (
	EnvKey              = "env"
	ForwarderNameKey    = "forwardername"
	ForwarderVersionKey = "forwarder_version"
	FunctionNameKey     = "functionname"
	ServiceKey          = "service"
	SourceOverriddenKey = "source_overridden"
)

type Tags []string

func (t Tags) MarshalJSON() ([]byte, error) {
	return json.Marshal(strings.Join(t, TagSeparator))
}

func (t *Tags) UnmarshalJSON(data []byte) error {
	var s string

	if err := json.Unmarshal(data, &s); err != nil {
		return err
	}
	if s == "" {
		*t = nil
		return nil
	}

	*t = strings.Split(s, TagSeparator)
	return nil
}

func (t *Tags) Add(key, value string) {
	*t = append(*t, key+KeyValueSeparator+value)
}

func (t *Tags) Has(key string) bool {
	for _, tag := range *t {
		if _, found := CutKey(tag, key); found {
			return true
		}
	}
	return false
}

func CutKey(tag, key string) (string, bool) {
	return strings.CutPrefix(tag, key+KeyValueSeparator)
}
