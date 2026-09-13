// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"cmp"
	"context"
	"encoding/json"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

type snsHandler struct {
	baseHandler
}

func (h *snsHandler) Handle(ctx context.Context, event json.RawMessage, out chan<- json.RawMessage) error {
	lambdaOrigin, err := model.GetLambdaOrigin(ctx)
	if err != nil {
		return fmt.Errorf("get lambda origin: %w", err)
	}

	message := string(event)
	if h.filterer.ShouldExclude(message) {
		return nil
	}

	source := cmp.Or(h.cfg.Source, sourceSNS)

	entry := model.NewLogEntry()
	entry.Message = message
	entry.Source = source
	entry.Service = h.cfg.Service
	entry.Tags = h.cfg.Tags
	entry.Metadata = lambdaOrigin

	return h.emit(ctx, out, entry)
}
