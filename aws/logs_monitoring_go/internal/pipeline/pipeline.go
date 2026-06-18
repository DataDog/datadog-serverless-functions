// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"errors"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"golang.org/x/sync/errgroup"
)

type Pipeline struct {
	handler   handling.Handler
	forwarder *forwarding.Forwarder
}

func New(handler handling.Handler, forwarder *forwarding.Forwarder) Pipeline {
	return Pipeline{handler: handler, forwarder: forwarder}
}

func (p Pipeline) Start(
	ctx context.Context,
	event parsing.Event,
) error {
	eg, ctx := errgroup.WithContext(ctx)

	entries := make(chan model.LogEntry)
	eg.Go(func() error {
		defer close(entries)
		if err := p.handler.Handle(ctx, event.Payload, entries); err != nil {
			return fmt.Errorf("handle: %w", err)
		}
		return nil
	})

	err := p.forwarder.Start(ctx, entries, forwarding.StorageTag(event.ContentType))
	if waitErr := eg.Wait(); waitErr != nil {
		return errors.Join(err, waitErr)
	}
	return err
}
