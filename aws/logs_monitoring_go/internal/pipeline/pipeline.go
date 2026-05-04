// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"encoding/json"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"golang.org/x/sync/errgroup"
)

func Start(
	ctx context.Context,
	event json.RawMessage,
	run *Run,
) error {
	g, ctx := errgroup.WithContext(ctx)

	entries := make(chan model.LogEntry)
	forwarder := forwarding.NewForwarder(run.Cfg, forwarding.Client, run.Storage)

	g.Go(func() error {
		defer close(entries)
		return run.Handler.Handle(ctx, event, entries)
	})

	g.Go(func() error {
		return forwarder.Start(ctx, entries)
	})

	return g.Wait()
}
