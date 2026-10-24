// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handler

import (
	"cmp"
	"context"
	"encoding/json"
)

type snsHandler struct {
	baseHandler
}

func (h *snsHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- json.RawMessage) error {
	message := string(event)
	if h.filterer.ShouldExclude(message) {
		return nil
	}

	entry := h.tmpl.NewEntry()
	entry.Message = message
	entry.Source = cmp.Or(entry.Source, sourceSNS)
	entry.Metadata = h.origin

	return h.emit(ctx, out, entry)
}
