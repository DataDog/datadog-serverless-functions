// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storing"
	"golang.org/x/sync/errgroup"
)

func Start(
	ctx context.Context,
	parsedEvents []parsing.ParsedEvent,
	cfg *config.Config,
) error {
	if len(parsedEvents) == 0 {
		return errors.New("no events to process")
	}

	eg, ctx := errgroup.WithContext(ctx)

	forwarder := forwarding.NewForwarder(cfg, httpclient.Client, storing.NewStorage(ctx, cfg))
	entries := make(chan model.LogEntry)

	eg.Go(func() error {
		defer close(entries)
		for _, parsedEvent := range parsedEvents {
			handler, err := handling.NewHandler(ctx, parsedEvent.ContentType, cfg)
			if err != nil {
				return fmt.Errorf("new handler: %w", err)
			}

			if err := handler.Handle(ctx, parsedEvent.Payload, entries); err != nil {
				return fmt.Errorf("handle: %w", err)
			}
		}
		return nil
	})

	err := forwarder.Start(ctx, entries, forwarding.StorageTag(parsedEvents[0].ContentType))
	if waitErr := eg.Wait(); waitErr != nil {
		return errors.Join(err, waitErr)
	}
	return err
}

func Retry(ctx context.Context, cfg *config.Config) {
	storage := storing.NewStorage(ctx, cfg)
	if storage == nil {
		return
	}

	forwarder := forwarding.NewForwarder(cfg, httpclient.Client, storage)

	keys, listErr := storage.List(ctx)
	if listErr != nil {
		slog.WarnContext(ctx, "failed to list stored batches", slog.Any("error", listErr))
		return
	}

	slog.InfoContext(ctx, "retrying stored batches", slog.Int("count", len(keys)))
	for _, key := range keys {
		payload, storageTag, getErr := storage.Get(ctx, key)
		if getErr != nil {
			slog.WarnContext(ctx, "failed to get stored batch", slog.String("key", key), slog.Any("error", getErr))
			continue
		}

		if sendErr := forwarder.Send(ctx, payload, storageTag); sendErr != nil {
			slog.WarnContext(ctx, "failed to send batch", slog.String("key", key), slog.Any("error", sendErr))
			continue
		}

		if deleteErr := storage.Delete(ctx, key); deleteErr != nil {
			slog.WarnContext(ctx, "failed to delete successfully sent batch from storage, will lead to log duplication", slog.String("key", key), slog.Any("error", deleteErr))
			continue
		}

		slog.DebugContext(ctx, "batch sent successfully", slog.String("key", key))
	}
}
