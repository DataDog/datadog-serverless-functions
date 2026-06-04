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
	"fmt"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
)

type EventBridgeHandler struct {
	cfg *Config
}

func NewEventBridge(cfg *Config) *EventBridgeHandler {
	return &EventBridgeHandler{
		cfg: cfg,
	}
}

func (h *EventBridgeHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error {
	lambdaOrigin, err := model.GetLambdaOrigin(ctx)
	if err != nil {
		return fmt.Errorf("get lambda origin: %w", err)
	}

	source, err := eventBridgeSource(event)
	if err != nil {
		return fmt.Errorf("source: %w", err)
	}

	switch source {
	case sourceSecurityHub:
		return h.securityHub(ctx, event, source, out, lambdaOrigin)
	default:
		return h.eventBridge(ctx, event, source, out, lambdaOrigin)
	}
}

func (h *EventBridgeHandler) eventBridge(ctx context.Context, event json.RawMessage, source string, out chan<- model.LogEntry, lambdaOrigin model.LambdaOrigin) error {
	message := string(event)
	if h.cfg.Filterer.ShouldExclude(message) {
		return nil
	}

	entry := h.newEntry(source, lambdaOrigin)
	entry.Message = h.cfg.Scrubber.Apply(message)

	return concurrent.SafeSender(ctx, out, entry)
}

func (h *EventBridgeHandler) securityHub(ctx context.Context, event json.RawMessage, source string, out chan<- model.LogEntry, lambdaOrigin model.LambdaOrigin) error {
	messages := separateFindings(event)
	if len(messages) == 0 {
		return h.eventBridge(ctx, event, source, out, lambdaOrigin)
	}

	base := h.newEntry(source, lambdaOrigin)
	for _, message := range messages {
		if h.cfg.Filterer.ShouldExclude(message) {
			continue
		}

		entry := base
		entry.Message = h.cfg.Scrubber.Apply(message)

		if err := concurrent.SafeSender(ctx, out, entry); err != nil {
			return err
		}
	}
	return nil
}

func (h *EventBridgeHandler) newEntry(source string, lambdaOrigin model.LambdaOrigin) model.LogEntry {
	entry := model.NewLogEntry()
	entry.Source = cmp.Or(h.cfg.Source, source)
	entry.Service = cmp.Or(h.cfg.Service, entry.Source)
	entry.Tags = h.cfg.Tags
	entry.Metadata = lambdaOrigin
	return entry
}

func eventBridgeSource(event json.RawMessage) (string, error) {
	dec := json.NewDecoder(bytes.NewReader(event))
	if err := parsing.SkipBrace(dec); err != nil {
		return "", err
	}

	if err := parsing.SkipToKey(dec, "source"); err != nil {
		return "", err
	}

	var rawSource string
	if err := dec.Decode(&rawSource); err != nil {
		return "", fmt.Errorf("decode: %w", err)
	}

	_, source, found := strings.Cut(rawSource, ".")
	if found {
		return source, nil
	}
	return sourceCloudwatch, nil
}
