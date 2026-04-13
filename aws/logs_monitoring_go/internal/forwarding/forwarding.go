// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"golang.org/x/sync/errgroup"
)

const numWorkers = 3

type Forwarder struct {
	config *config.Config
	client *http.Client
}

func NewForwarder(config *config.Config, client *http.Client) Forwarder {
	return Forwarder{
		config: config,
		client: client,
	}
}

func (f Forwarder) Forward(ctx context.Context, in <-chan []byte) error {
	g, ctx := errgroup.WithContext(ctx)

	for range numWorkers {
		g.Go(func() error {
			for {
				body, ok, err := concurrent.SafeReader(ctx, in)
				if err != nil {
					return err
				}
				if !ok {
					return nil
				}

				if err := f.send(ctx, body); err != nil {
					return err
				}
			}
		})
	}

	return g.Wait()
}

func (f Forwarder) send(ctx context.Context, body []byte) error {
	var compressedBody bytes.Buffer
	zw := gzip.NewWriter(&compressedBody)
	if _, err := zw.Write(body); err != nil {
		return fmt.Errorf("compressing body: %w", err)
	}
	if err := zw.Close(); err != nil {
		return fmt.Errorf("closing gzip writer: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, f.config.IntakeURL, bytes.NewReader(compressedBody.Bytes()))
	if err != nil {
		return err
	}

	req.Header.Set("DD-API-KEY", f.config.APIKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Content-Encoding", "gzip")
	req.Header.Set("DD-EVP-ORIGIN", "aws_forwarder")
	req.Header.Set("DD-EVP-ORIGIN-VERSION", config.ForwarderVersion)

	resp, err := f.client.Do(req)
	if err != nil {
		return fmt.Errorf("sending to intake: %w", err)
	}
	defer func() {
		if _, err := io.Copy(io.Discard, resp.Body); err != nil {
			slog.Warn("failed to drain response body", slog.Any("error", err))
		}
		if err := resp.Body.Close(); err != nil {
			slog.Warn("failed to close response body", slog.Any("error", err))
		}
	}()

	if resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("unexpected status from intake: %s", resp.Status)
	}

	return nil
}
