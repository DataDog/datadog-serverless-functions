// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/processing"
	"golang.org/x/sync/errgroup"
)

func Run[T any](
	ctx context.Context,
	event json.RawMessage,
	cfg *config.Config,
	handler func(context.Context, json.RawMessage, *config.Config, chan<- T) error,
) error {
	var g errgroup.Group

	entries := make(chan T)
	batches := make(chan []byte)

	batcher := processing.NewBatcher[T]()
	forwarder := forwarding.NewForwarder(cfg, &http.Client{
		Timeout: 10 * time.Second,
	})

	g.Go(func() error {
		defer close(entries)
		return handler(ctx, event, cfg, entries)
	})

	g.Go(func() error {
		defer close(batches)
		return batcher.Batch(ctx, entries, batches)
	})

	g.Go(func() error {
		return forwarder.Forward(ctx, batches)
	})

	return g.Wait()
}
