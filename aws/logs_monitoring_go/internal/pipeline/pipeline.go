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
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"golang.org/x/sync/errgroup"
)

type Pipeline struct {
	cfg       *config.Config
	filter    *filtering.Filter
	scrubber  *scrubbing.Scrubber
	forwarder *forwarding.Forwarder
}

func New(
	cfg *config.Config,
	filter *filtering.Filter,
	scrubber *scrubbing.Scrubber,
	forwarder *forwarding.Forwarder,
) *Pipeline {
	return &Pipeline{
		cfg:       cfg,
		filter:    filter,
		scrubber:  scrubber,
		forwarder: forwarder,
	}
}

func (p *Pipeline) Start(
	ctx context.Context,
	parsedEvents []parsing.ParsedEvent,
) error {
	contentType := parsedEvents[0].ContentType
	if contentType == parsing.ContentTypeRetry {
		p.forwarder.Retry(ctx)
	}

	eg, ctx := errgroup.WithContext(ctx)

	entries := make(chan model.LogEntry)

	eg.Go(func() error {
		defer close(entries)
		for _, parsedEvent := range parsedEvents {
			handler, err := handling.NewHandler(ctx, parsedEvent.ContentType, p.cfg)
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
