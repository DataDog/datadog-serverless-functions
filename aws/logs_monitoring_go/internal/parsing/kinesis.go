// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/aws/aws-lambda-go/events"
)

func HandleKinesis(ctx context.Context, event json.RawMessage, cfg *config.Config, out chan<- model.CloudwatchLogEntry) error {
	var kinesisEvent events.KinesisEvent
	if err := json.Unmarshal(event, &kinesisEvent); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	for _, record := range kinesisEvent.Records {
		cwEvent := events.CloudwatchLogsEvent{
			AWSLogs: events.CloudwatchLogsRawData{
				Data: base64.StdEncoding.EncodeToString(record.Kinesis.Data),
			},
		}

		cwRaw, err := json.Marshal(cwEvent)
		if err != nil {
			return fmt.Errorf("marshal cloudwatch event from kinesis: %w", err)
		}

		if err := HandleCloudwatchLogs(ctx, cwRaw, cfg, out); err != nil {
			slog.WarnContext(ctx, "skipping kinesis record", "error", err)
			continue
		}
	}
	return nil
}
