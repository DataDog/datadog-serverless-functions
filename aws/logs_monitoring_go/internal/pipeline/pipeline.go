// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"errors"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
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

	entries := make(chan model.LogEntry)
	forwarder := forwarding.NewForwarder(cfg, httpclient.Client, forwarding.StorageFromContentType(parsedEvents[0].ContentType))

	eg.Go(func() error {
		defer close(entries)
		for _, parsedEvent := range parsedEvents {
			handler, err := handling.NewHandler(parsedEvent.ContentType, cfg)
			if err != nil {
				return fmt.Errorf("new handler: %w", err)
			}

			if err := handler.Handle(ctx, parsedEvent.Payload, entries); err != nil {
				return fmt.Errorf("handle: %w", err)
			}
		}
		return nil
	})

	err := forwarder.Start(ctx, entries)
	if waitErr := eg.Wait(); waitErr != nil {
		return errors.Join(err, waitErr)
	}
	return err
}
