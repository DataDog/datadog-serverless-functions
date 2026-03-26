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
