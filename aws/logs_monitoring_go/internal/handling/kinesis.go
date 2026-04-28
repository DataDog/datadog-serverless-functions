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

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

type KinesisHandler struct {
	cfg *config.Config
}

func NewKinesis(cfg *config.Config) *KinesisHandler {
	return &KinesisHandler{
		cfg: cfg,
	}
}

func (h KinesisHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
	var kinesisEvent events.KinesisEvent
	if err := json.Unmarshal(event, &kinesisEvent); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	cw := CloudwatchHandler{cfg: h.cfg}
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
