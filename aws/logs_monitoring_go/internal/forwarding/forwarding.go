// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batching"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"golang.org/x/sync/errgroup"
)

const MaxConcurrency = 5

type Forwarder struct {
	cfg     *config.Config
	client  *http.Client
	storage string
}

func NewForwarder(cfg *config.Config, client *http.Client, storage string) Forwarder {
	return Forwarder{
		cfg:     cfg,
		client:  client,
		storage: storage,
	}
}

func (f Forwarder) Start(ctx context.Context, in <-chan model.LogEntry) error {
	batches := make(chan []byte, MaxConcurrency)
	batcher := batching.NewBatcher()

	producerErrCh := make(chan error, 1)
	go func() {
		defer close(batches)
		producerErrCh <- batcher.Batch(ctx, in, batches)
	}()

	var eg errgroup.Group
	eg.SetLimit(MaxConcurrency)

	var errs []error
	var mu sync.Mutex

	for {
		body, ok, err := concurrent.SafeReader(ctx, batches)
		if err != nil {
			mu.Lock()
			errs = append(errs, err)
			mu.Unlock()
		}
		if !ok {
			break
		}

		eg.Go(func() error {
			if err := f.Send(ctx, body); err != nil {
				mu.Lock()
				errs = append(errs, err)
				mu.Unlock()
			}
			return nil
		})
	}
	_ = eg.Wait()

	return errors.Join(append(errs, <-producerErrCh)...)
}

func (f Forwarder) Send(ctx context.Context, payload []byte) error {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, f.cfg.IntakeURL, bytes.NewReader(payload))
	if err != nil {
		return err
	}

	req.Header.Set("DD-API-KEY", f.cfg.APIKey)
	req.Header.Set("DD-EVP-ORIGIN", "aws_forwarder")
	req.Header.Set("DD-EVP-ORIGIN-VERSION", config.ForwarderVersion)
	req.Header.Set("Content-Type", "application/json")
	if f.storage != "" {
		req.Header.Set("DD-STORAGE-TAG", f.storage)
	}

	resp, err := f.client.Do(req)
	if err != nil {
		return fmt.Errorf("intake: %w", err)
	}
	defer drainClose(resp)

	if resp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(resp.Body)
		if len(body) > 0 {
			return fmt.Errorf("intake (http/%d): %s", resp.StatusCode, string(body))
		}
		return fmt.Errorf("intake (http/%d)", resp.StatusCode)
	}

	return nil
}

func drainClose(resp *http.Response) {
	if _, err := io.Copy(io.Discard, resp.Body); err != nil {
		slog.Warn("draining response body", slog.Any("error", err))
	}
	if err := resp.Body.Close(); err != nil {
		slog.Warn("closing response body", slog.Any("error", err))
	}
}
