// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"errors"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"golang.org/x/sync/errgroup"
)

type Pipeline struct {
	hcfg      handling.Config
	scrubber  *scrubbing.Scrubber
	filterer  *filtering.Filterer
	forwarder *forwarding.Forwarder
}

func New(
	hcfg handling.Config,
	scrubber *scrubbing.Scrubber,
	filterer *filtering.Filterer,
	forwarder *forwarding.Forwarder,
) *Pipeline {
	return &Pipeline{
		hcfg:      hcfg,
		scrubber:  scrubber,
		filterer:  filterer,
		forwarder: forwarder,
	}
}

func (p *Pipeline) Start(
	ctx context.Context,
	events []parsing.Event,
) error {
	contentType := events[0].ContentType
	if contentType == parsing.ContentTypeRetry {
		if err := p.forwarder.Retry(ctx); err != nil {
			return fmt.Errorf("retry: %w", err)
		}
		return nil
	}

	eg, ctx := errgroup.WithContext(ctx)

	entries := make(chan model.LogEntry)

	eg.Go(func() error {
		defer close(entries)
		for _, parsedEvent := range events {
			handler, err := handling.NewHandler(ctx, p.hcfg, p.scrubber, p.filterer, parsedEvent.ContentType)
			if err != nil {
				return fmt.Errorf("new handler: %w", err)
			}

			if err := handler.Handle(ctx, parsedEvent.Payload, entries); err != nil {
				return fmt.Errorf("handle: %w", err)
			}
		}
		return nil
	})

	err := p.forwarder.Start(ctx, entries, forwarding.StorageTag(contentType))
	if waitErr := eg.Wait(); waitErr != nil {
		return errors.Join(err, waitErr)
	}
	return err
}
