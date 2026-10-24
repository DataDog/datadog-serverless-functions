// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filterer"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarder"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handler"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parser"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubber"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"golang.org/x/sync/errgroup"
)

type Result struct {
	SQSBatch    bool
	Unprocessed []string
}

type Pipeline struct {
	hcfg      handler.Config
	scrubber  *scrubber.Scrubber
	filterer  *filterer.Filterer
	forwarder *forwarder.Forwarder
	s3Client  sdkclient.S3
}

func New(
	hcfg handler.Config,
	scrub *scrubber.Scrubber,
	filter *filterer.Filterer,
	fwd *forwarder.Forwarder,
	s3Client sdkclient.S3,
) Pipeline {
	return Pipeline{
		hcfg:      hcfg,
		scrubber:  scrub,
		filterer:  filter,
		forwarder: fwd,
		s3Client:  s3Client,
	}
}

func (p Pipeline) Start(ctx context.Context, origin model.LambdaOrigin, awsevent json.RawMessage) (Result, error) {
	if parser.IsSQS(awsevent) {
		events, err := parser.SQS(awsevent)
		if err != nil {
			return Result{SQSBatch: true}, err
		}

		slog.DebugContext(ctx, "SQS event dispatched", slog.Int("records", len(events)))
		return p.startSQS(ctx, origin, events)
	}

	event, err := parser.Parse(awsevent)
	if err != nil {
		return Result{}, fmt.Errorf("parse: %w", err)
	}

	if event.ContentType == parser.ContentTypeRetry {
		slog.DebugContext(ctx, "retry event received, processing stored batches")
		return Result{}, p.forwarder.Retry(ctx)
	}

	return Result{}, p.run(ctx, origin, event)
}

func (p Pipeline) startSQS(ctx context.Context, origin model.LambdaOrigin, events []parser.SQSEvent) (Result, error) {
	result := Result{SQSBatch: true}

	for i, event := range events {
		err := p.run(ctx, origin, event.Event)
		if err == nil {
			continue
		}

		slog.DebugContext(ctx, "SQS batch item failures",
			slog.String("message_id", event.SQSReceiptHandle),
			slog.Int("messages sent back", len(events)-i),
		)
		for _, remaining := range events[i:] {
			result.Unprocessed = append(result.Unprocessed, remaining.SQSReceiptHandle)
		}

		return result, err
	}

	return result, nil
}

func (p Pipeline) run(ctx context.Context, origin model.LambdaOrigin, event parser.Event) error {
	slog.DebugContext(ctx, "processing event", slog.String("content_type", event.ContentType.String()))

	eg, ctx := errgroup.WithContext(ctx)

	entries := make(chan json.RawMessage)
	eg.Go(func() error {
		defer close(entries)
		h, err := handler.New(p.hcfg, origin, p.scrubber, p.filterer, p.s3Client, event.ContentType)
		if err != nil {
			return fmt.Errorf("new handler: %w", err)
		}

		if err := h.Handle(ctx, event.Payload, entries); err != nil {
			return fmt.Errorf("handle: %w", err)
		}
		return nil
	})

	err := p.forwarder.Start(ctx, entries, forwarder.StorageTag(event.ContentType))
	if waitErr := eg.Wait(); waitErr != nil {
		return errors.Join(err, waitErr)
	}

	return err
}
