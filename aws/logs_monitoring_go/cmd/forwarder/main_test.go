// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"compress/gzip"
	"encoding/json"
	"flag"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handler"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/version"
	"github.com/stretchr/testify/require"
)

var update = flag.Bool("update", false, "update .golden files")

const testAPIKey = "abcdefghijklmnopqrstuvwxyz012345"

func load(t *testing.T, path string) json.RawMessage {
	t.Helper()

	data, err := os.ReadFile(path)
	require.NoError(t, err)

	gzipped := testutil.MustGzip(t, data)
	name := filepath.Base(path)

	switch {
	case strings.HasPrefix(name, "cloudwatch"):
		return testutil.MustCloudwatchEvent(t, gzipped)
	case strings.HasPrefix(name, "kinesis"):
		return testutil.MustKinesisEvent(t, gzipped)
	default:
		return data
	}
}

func TestHandleRequest(t *testing.T) {
	inputs, err := filepath.Glob("testdata/*.input.json")
	require.NoError(t, err)
	require.NotEmpty(t, inputs, "no .input.json files found in testdata/")

	for _, input := range inputs {
		name := strings.TrimSuffix(filepath.Base(input), ".input.json")
		golden := strings.TrimSuffix(input, ".input.json") + ".golden.json"

		t.Run(name, func(t *testing.T) {
			rec := newRecorder(t)
			cfg := &config.Config{
				IntakeURL:        rec.URL,
				CompressionLevel: gzip.DefaultCompression,
			}
			ctx := testutil.LambdaContext(t)
			event := load(t, input)

			_, err := handleRequest(cfg, handler.Config{}, testAPIKey, rec.Client())(ctx, event)

			require.NoError(t, err)
			require.NotEmpty(t, rec.request, "recorder received no requests")
			assertGolden(t, golden, rec.request)
		})
	}
}

func assertGolden(t *testing.T, goldenPath string, actual any) {
	t.Helper()

	actualJSON, err := json.MarshalIndent(actual, "", "  ")
	require.NoError(t, err)

	actualJSON = append(actualJSON, '\n')

	if *update {
		require.NoError(t, os.WriteFile(goldenPath, actualJSON, 0o644))
		t.Logf("updated %s", goldenPath)
		return
	}

	expected, err := os.ReadFile(goldenPath)
	require.NoError(t, err, "%q golden file missing, run with -update to create it", goldenPath)
	require.JSONEq(t, normalizeTags(t, expected), normalizeTags(t, actualJSON))
}

func normalizeTags(t *testing.T, data []byte) string {
	t.Helper()

	var payload map[string]any
	require.NoError(t, json.Unmarshal(data, &payload))

	entries, ok := payload["body"].([]any)
	if !ok {
		return string(data)
	}

	for _, entry := range entries {
		fields, ok := entry.(map[string]any)
		if !ok {
			continue
		}

		tags, ok := fields[model.TagsJSONKey].(string)
		if !ok {
			continue
		}

		sorted := strings.Split(tags, model.TagSeparator)
		slices.Sort(sorted)
		fields[model.TagsJSONKey] = strings.Join(sorted, model.TagSeparator)
	}

	normalized, err := json.Marshal(payload)
	require.NoError(t, err)

	return string(normalized)
}

func TestNewHandlerConfig(t *testing.T) {
	t.Parallel()

	forwarderTags := model.Tags{
		model.ForwarderNameKey + model.KeyValueSeparator + "my-forwarder",
		model.ForwarderVersionKey + model.KeyValueSeparator + version.Forwarder,
	}

	tests := map[string]struct {
		cfg         config.Config
		wantService string
		wantTags    model.Tags
	}{
		"identity tags always added": {
			wantTags: forwarderTags,
		},
		"source override adds tag": {
			cfg:      config.Config{Source: "my-source"},
			wantTags: append(model.Tags{"source_overridden:true"}, forwarderTags...),
		},
		"custom tags precede identity tags": {
			cfg:      config.Config{Tags: "team:backend,env:prod"},
			wantTags: append(model.Tags{"team:backend", "env:prod"}, forwarderTags...),
		},
		"service extracted out of tags": {
			cfg:         config.Config{Tags: "team:backend,service:my-app"},
			wantService: "my-app",
			wantTags:    append(model.Tags{"team:backend"}, forwarderTags...),
		},
		"source and custom tags": {
			cfg:         config.Config{Source: "my-source", Tags: "service:my-app,env:prod"},
			wantService: "my-app",
			wantTags:    append(model.Tags{"env:prod", "source_overridden:true"}, forwarderTags...),
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got := newHandlerConfig(&tc.cfg, "My-Forwarder")

			require.Equal(t, tc.wantService, got.Service)
			require.Equal(t, tc.cfg.Source, got.Source)
			require.Equal(t, tc.wantTags, got.Tags)
		})
	}
}
