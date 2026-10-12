// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"cmp"
	"io"
	"log/slog"
)

const defaultLogLevel = "INFO"

func initLogger(w io.Writer, level string) {
	parsed := slog.LevelInfo
	err := parsed.UnmarshalText([]byte(cmp.Or(level, defaultLogLevel)))

	slog.SetDefault(slog.New(slog.NewJSONHandler(w, &slog.HandlerOptions{Level: parsed})))

	if err != nil {
		slog.Warn("invalid log level, using default", slog.String("value", level), slog.String("default", defaultLogLevel))
	}
}
