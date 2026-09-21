// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

type Handler interface {
	Handle(ctx context.Context, event json.RawMessage, out chan<- json.RawMessage) error
}

type Config struct {
	Service             string
	Source              string
	Tags                model.Tags
	S3MultilineLogRegex *regexp.Regexp
}

func NewHandler(hcfg Config, scrubber *scrubbing.Scrubber, filterer *filtering.Filterer, ct parsing.ContentType) (Handler, error) {
	base := newBase(&hcfg, scrubber, filterer)

	switch ct {

	case parsing.ContentTypeCloudwatchLogs:
		return &cloudwatchHandler{baseHandler: base}, nil

	case parsing.ContentTypeS3:
		client, err := sdkclient.GetS3()
		if err != nil {
			return nil, err
		}
		return newS3(base, client), nil

	case parsing.ContentTypeKinesis:
		return &kinesisHandler{baseHandler: base}, nil

	case parsing.ContentTypeEventBridge:
		return &eventBridgeHandler{baseHandler: base}, nil

	case parsing.ContentTypeSNS:
		return &snsHandler{baseHandler: base}, nil

	default:
		return nil, fmt.Errorf("unsupported content type: %v", ct)
	}
}

type baseHandler struct {
	cfg      *Config
	scrubber *scrubbing.Scrubber
	filterer *filtering.Filterer
}

func newBase(cfg *Config, scrubber *scrubbing.Scrubber, filterer *filtering.Filterer) baseHandler {
	return baseHandler{cfg: cfg, scrubber: scrubber, filterer: filterer}
}

func (h *baseHandler) emit(ctx context.Context, out chan<- json.RawMessage, entry model.LogEntry) error {
	entry.Message = h.scrubber.Apply(entry.Message)

	item, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("marshal log entry: %w", err)
	}
	return concurrent.SafeSender(ctx, out, item)
}
