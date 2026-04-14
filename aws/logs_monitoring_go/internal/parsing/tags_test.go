// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"encoding/json"
	"slices"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

func TestExtractFromMessage(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		message     string
		wantTags    model.Tags
		wantService string
		wantMessage string
	}{
		"empty string": {
			message:     "",
			wantTags:    nil,
			wantService: "",
			wantMessage: "",
		},
		"plain text": {
			message:     "ERROR something went wrong",
			wantTags:    nil,
			wantService: "",
			wantMessage: "ERROR something went wrong",
		},
		"invalid json": {
			message:     `{not valid json}`,
			wantTags:    nil,
			wantService: "",
			wantMessage: `{not valid json}`,
		},
		"json without ddtags": {
			message:     `{"level":"INFO","msg":"hello"}`,
			wantTags:    nil,
			wantService: "",
			wantMessage: `{"level":"INFO","msg":"hello"}`,
		},
		"ddtags is not a string": {
			message:     `{"ddtags":["tag1","tag2"]}`,
			wantTags:    nil,
			wantService: "",
			wantMessage: `{"ddtags":["tag1","tag2"]}`,
		},
		"single tag": {
			message:     `{"msg":"hello","ddtags":"env:prod"}`,
			wantTags:    model.Tags{"env:prod"},
			wantService: "",
			wantMessage: `{"msg":"hello"}`,
		},
		"multiple tags": {
			message:     `{"msg":"hello","ddtags":"env:prod,team:backend"}`,
			wantTags:    model.Tags{"env:prod", "team:backend"},
			wantService: "",
			wantMessage: `{"msg":"hello"}`,
		},
		"tags with spaces are cleaned": {
			message:     `{"msg":"hello","ddtags":"env:prod, team:backend, version:1.0"}`,
			wantTags:    model.Tags{"env:prod", "team:backend", "version:1.0"},
			wantService: "",
			wantMessage: `{"msg":"hello"}`,
		},
		"service tag extracted": {
			message:     `{"msg":"hello","ddtags":"service:my-app,env:prod"}`,
			wantTags:    model.Tags{"env:prod"},
			wantService: "my-app",
			wantMessage: `{"msg":"hello"}`,
		},
		"service only": {
			message:     `{"msg":"hello","ddtags":"service:my-app"}`,
			wantTags:    nil,
			wantService: "my-app",
			wantMessage: `{"msg":"hello"}`,
		},
		"first service wins": {
			message:     `{"msg":"hello","ddtags":"service:first,service:second,env:prod"}`,
			wantTags:    model.Tags{"env:prod"},
			wantService: "first",
			wantMessage: `{"msg":"hello"}`,
		},
		"ddtags is empty string": {
			message:     `{"msg":"hello","ddtags":""}`,
			wantTags:    model.Tags{""},
			wantService: "",
			wantMessage: `{"msg":"hello"}`,
		},
		"ddtags only field in json": {
			message:     `{"ddtags":"env:prod"}`,
			wantTags:    model.Tags{"env:prod"},
			wantService: "",
			wantMessage: `{}`,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			gotTags, gotService, gotMessage := extractFromMessage(tc.message)

			if !slices.Equal(gotTags, tc.wantTags) {
				t.Errorf("tags: got %v, want %v", gotTags, tc.wantTags)
			}
			if gotService != tc.wantService {
				t.Errorf("service: got %q, want %q", gotService, tc.wantService)
			}
			if gotMessage != tc.wantMessage {
				t.Errorf("message: got %q, want %q", gotMessage, tc.wantMessage)
			}
		})
	}
}

func FuzzExtractFromMessage(f *testing.F) {
	seeds := []string{
		"",
		"plain text, not json",
		`{not valid json}`,
		`{"msg":"hello"}`,
		`{"ddtags":["tag1","tag2"]}`,
		`{"ddtags":42}`,
		`{"msg":"hello","ddtags":"env:prod"}`,
		`{"msg":"hello","ddtags":"env:prod, team:backend, version:1.0"}`,
		`{"msg":"hello","ddtags":"service:my-app,env:prod"}`,
		`{"msg":"hello","ddtags":"service:my-app"}`,
		`{"msg":"hello","ddtags":"service:first,service:second,env:prod"}`,
		`{"msg":"hello","ddtags":""}`,
		`{"ddtags":"env:prod"}`,
	}
	for _, seed := range seeds {
		f.Add(seed)
	}

	f.Fuzz(func(t *testing.T, message string) {
		tags, _, outMessage := extractFromMessage(message)

		if outMessage != message {
			var parsed map[string]any
			if err := json.Unmarshal([]byte(outMessage), &parsed); err != nil {
				t.Errorf("output message is not valid JSON: %v", err)
			}
			if _, ok := parsed[DdtagsKey]; ok {
				t.Errorf("output message still contains %q key", DdtagsKey)
			}
		}

		for _, tag := range tags {
			if strings.HasPrefix(tag, "service:") {
				t.Errorf("tag %q should have been extracted as service, not returned in tags", tag)
			}
		}
	})
}
