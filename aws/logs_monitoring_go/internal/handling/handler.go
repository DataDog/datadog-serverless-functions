// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"context"
	"encoding/json"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
)

var Handlers = make(map[parsing.InvocationSource]Handler)

type Handler interface {
	Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error
}

func Register(invocation parsing.InvocationSource, handler Handler) {
	Handlers[invocation] = handler
}
