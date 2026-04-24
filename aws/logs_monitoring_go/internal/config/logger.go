// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"log/slog"
	"os"
)

func initLogger(level string) {
	var slogLevel slog.Level

	if err := slogLevel.UnmarshalText([]byte(level)); err != nil {
		slog.Error(err.Error(), slog.String("level", level))
		slogLevel = slog.LevelInfo
	}

	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stderr, &slog.HandlerOptions{
		Level: slogLevel,
	})))
}
