// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
)

type Handler interface {
	Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error
}

func NewHandler(ct parsing.ContentType, cfg *config.Config) (Handler, error) {
	switch ct {
	case parsing.ContentTypeCloudwatchLogs:
		return NewCloudwatch(cfg), nil
	case parsing.ContentTypeS3:
		return NewS3(cfg), nil
	case parsing.ContentTypeKinesis:
		return NewKinesis(cfg), nil
	case parsing.ContentTypeEventBridge:
		return NewEventBridge(cfg), nil
	case parsing.ContentTypeSNS:
		return NewSNS(cfg), nil
	default:
		return nil, fmt.Errorf("unsupported content type: %v", ct)
	}
}
