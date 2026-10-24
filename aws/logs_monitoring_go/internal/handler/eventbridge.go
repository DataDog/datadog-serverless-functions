// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handler

import (
	"cmp"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

type eventBridgeHandler struct {
	baseHandler
}

func (h *eventBridgeHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- json.RawMessage) error {
	source, err := eventBridgeSource(event)
	if err != nil {
		return err
	}
	slog.DebugContext(ctx, "processing eventbridge event", slog.String("source", source))

	switch source {
	case sourceSecurityHub:
		return h.securityHub(ctx, event, source, out)
	default:
		return h.eventBridge(ctx, event, source, out)
	}
}

func (h *eventBridgeHandler) eventBridge(ctx context.Context, event json.RawMessage, source string, out chan<- json.RawMessage) error {
	message := string(event)
	if h.filterer.ShouldExclude(message) {
		return nil
	}

	entry := h.newEntry(source)
	entry.Message = message

	return h.emit(ctx, out, entry)
}

func (h *eventBridgeHandler) securityHub(ctx context.Context, event json.RawMessage, source string, out chan<- json.RawMessage) error {
	messages := separateFindings(event)
	if len(messages) == 0 {
		return h.eventBridge(ctx, event, source, out)
	}

	base := h.newEntry(source)
	for _, message := range messages {
		if h.filterer.ShouldExclude(message) {
			continue
		}

		entry := base
		entry.Message = message

		if err := h.emit(ctx, out, entry); err != nil {
			return err
		}
	}
	return nil
}

func (h *eventBridgeHandler) newEntry(source string) model.LogEntry {
	entry := h.tmpl.NewEntry()
	entry.Source = cmp.Or(entry.Source, source)
	entry.Service = cmp.Or(entry.Service, entry.Source)
	entry.Metadata = h.origin
	return entry
}

func eventBridgeSource(event json.RawMessage) (string, error) {
	var s struct {
		Source string `json:"source"`
	}

	if err := json.Unmarshal(event, &s); err != nil {
		return "", fmt.Errorf("unmarshal: %w", err)
	}

	if s.Source == "" {
		return "", errors.New("eventbridge source not found")
	}

	_, source, found := strings.Cut(s.Source, ".")
	if found {
		return source, nil
	}
	return sourceCloudwatch, nil
}
