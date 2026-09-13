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

	"github.com/aws/aws-lambda-go/events"
)

type kinesisHandler struct {
	baseHandler
}

func (h *kinesisHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- json.RawMessage) error {
	var kinesisEvent events.KinesisEvent
	if err := json.Unmarshal(event, &kinesisEvent); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	cw := cloudwatchHandler{baseHandler: h.baseHandler}
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
