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
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/testutil"
	"github.com/stretchr/testify/require"
)

var update = flag.Bool("update", false, "update .golden files")

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
				APIKey:           "abcdefghijklmnopqrstuvwxyz012345",
				IntakeURL:        rec.URL,
				CompressionLevel: gzip.DefaultCompression,
			}
			ctx := testutil.LambdaContext(t)
			event := load(t, input)

			_, err := handleRequest(cfg, rec.Server.Client())(ctx, event)

			require.NoError(t, err)
			assertGolden(t, golden, rec.snapshot(t))
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
	require.JSONEq(t, string(expected), string(actualJSON))
}
