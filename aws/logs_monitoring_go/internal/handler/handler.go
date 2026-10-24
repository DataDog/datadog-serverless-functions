// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handler

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filterer"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parser"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubber"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

type Handler interface {
	Handle(ctx context.Context, event json.RawMessage, out chan<- json.RawMessage) error
}

type Config struct {
	Template            Template
	S3MultilineLogRegex *regexp.Regexp
}

func New(hcfg Config, origin model.LambdaOrigin, scrub *scrubber.Scrubber, filter *filterer.Filterer, s3Client sdkclient.S3, ct parser.ContentType) (Handler, error) {
	base := newBase(&hcfg, origin, scrub, filter)

	switch ct {

	case parser.ContentTypeCloudwatchLogs:
		return &cloudwatchHandler{baseHandler: base}, nil

	case parser.ContentTypeS3:
		return newS3(base, s3Client), nil

	case parser.ContentTypeKinesis:
		return &kinesisHandler{baseHandler: base}, nil

	case parser.ContentTypeEventBridge:
		return &eventBridgeHandler{baseHandler: base}, nil

	case parser.ContentTypeSNS:
		return &snsHandler{baseHandler: base}, nil

	default:
		return nil, fmt.Errorf("unsupported content type: %v", ct)
	}
}

type baseHandler struct {
	cfg      *Config
	tmpl     Template
	origin   model.LambdaOrigin
	scrubber *scrubber.Scrubber
	filterer *filterer.Filterer
}

func newBase(cfg *Config, origin model.LambdaOrigin, scrub *scrubber.Scrubber, filter *filterer.Filterer) baseHandler {
	return baseHandler{cfg: cfg, tmpl: cfg.Template, origin: origin, scrubber: scrub, filterer: filter}
}

func (h *baseHandler) emit(ctx context.Context, out chan<- json.RawMessage, entry model.LogEntry) error {
	item, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("marshal log entry: %w", err)
	}

	return concurrent.SafeSender(ctx, out, h.scrubber.Apply(item))
}
