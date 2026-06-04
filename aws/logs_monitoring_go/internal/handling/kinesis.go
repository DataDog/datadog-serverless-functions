// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"github.com/aws/aws-lambda-go/events"
)

type kinesisHandler struct {
	cfg      *Config
	scrubber *scrubbing.Scrubber
	filterer *filtering.Filterer
}

func newKinesis(cfg *Config, scrubber *scrubbing.Scrubber, filterer *filtering.Filterer) *kinesisHandler {
	return &kinesisHandler{
		cfg:      cfg,
		scrubber: scrubber,
		filterer: filterer,
	}
}

func (h *kinesisHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
	var kinesisEvent events.KinesisEvent
	if err := json.Unmarshal(event, &kinesisEvent); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	cw := cloudwatchHandler{cfg: h.cfg, scrubber: h.scrubber, filterer: h.filterer}
	for i, record := range kinesisEvent.Records {
		cwData, err := decompressCloudwatchLogs(record.Kinesis.Data)
		if err != nil {
			slog.WarnContext(ctx, "skipping kinesis record", slog.Int("i", i), slog.Any("error", err))
			continue
		}

		if err := cw.handleCloudwatchData(ctx, cwData, out); err != nil {
			slog.WarnContext(ctx, "skipping kinesis record", slog.Int("i", i), slog.Any("error", err))
			continue
		}
	}
	return nil
}
