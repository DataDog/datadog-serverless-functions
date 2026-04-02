// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
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

	g.Go(func() error {
		defer close(entries)
		handler(ctx, event, cfg, entries)
		return nil
	})

	g.Go(func() error {
		for entry := range entries {
			fmt.Println(entry)
		}
		return nil
	})

	return g.Wait()
}
