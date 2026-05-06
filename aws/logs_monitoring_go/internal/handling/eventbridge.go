// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"bytes"
	"cmp"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

type EventBridgeHandler struct {
	cfg *config.Config
}

func NewEventBridge(cfg *config.Config) *EventBridgeHandler {
	return &EventBridgeHandler{
		cfg: cfg,
	}
}

func (h *EventBridgeHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
	lambdaOrigin, err := model.GetLambdaOrigin(ctx)
	if err != nil {
		return fmt.Errorf("get lambda origin: %w", err)
	}

	ebSource, err := decodeEventBridgeSource(event)
	if err != nil {
		return err
	}
	source := cmp.Or(h.cfg.Source, ebSource)
	service := cmp.Or(h.cfg.Service, source)

	entry := model.NewLogEntry()
	entry.Message = string(event)
	entry.Source = source
	entry.Service = service
	entry.Tags = h.cfg.Tags
	entry.Metadata = lambdaOrigin

	if h.cfg.Filter.ShouldExclude(entry.Message) {
		return nil
	}

	entry.Message = h.cfg.Scrubber.Scrub(entry.Message)
	return concurrent.SafeSender(ctx, out, entry)
}

func decodeEventBridgeSource(event json.RawMessage) (string, error) {
	dec := json.NewDecoder(bytes.NewReader(event))

	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return "", errors.New("decode eventbridge source: expected '{'")
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return "", fmt.Errorf("decode eventbridge source: read key: %w", err)
		}
		if key == "source" {
			var source string
			if err := dec.Decode(&source); err != nil {
				return "", fmt.Errorf("decode eventbridge source: %w", err)
			}
			return eventBridgeSource(source), nil
		}
		var skip json.RawMessage
		if err := dec.Decode(&skip); err != nil {
			return "", fmt.Errorf("decode eventbridge source: skip field: %w", err)
		}
	}

	return "", nil
}

func eventBridgeSource(source string) string {
	_, after, found := strings.Cut(source, ".")
	if found {
		return after
	}
	return sourceCloudwatch
}
