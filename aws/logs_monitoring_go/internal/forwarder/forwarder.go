// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarder

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync"
	"sync/atomic"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batcher"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storage"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/version"
	"golang.org/x/sync/errgroup"
)

const (
	ddRetryHeader = "DD-RETRY-TAG"
	retryReserve  = httpclient.RequestTimeout + 2*time.Second
)

const (
	maxLogSize         = 1000 * 1000
	maxBatchSize       = 5 * 1000 * 1000
	maxLogsPerBatch    = 1000
	maxBatchesInMemory = 12
)

var bufPool = sync.Pool{
	New: func() any { return new(bytes.Buffer) },
}

type Delivery int

const (
	ToIntake Delivery = iota
	ToStorage
)

type Forwarder struct {
	cfg      Config
	client   *http.Client
	storage  storage.Storage
	gzipPool *sync.Pool
	header   http.Header
}

type Config struct {
	APIKey                    string
	IntakeURL                 string
	CompressionLevel          int
	StepFunctionsTraceEnabled bool
}

func New(cfg Config, client *http.Client, store storage.Storage) *Forwarder {
	header := http.Header{
		"DD-API-KEY":            []string{cfg.APIKey},
		"DD-EVP-ORIGIN":         []string{"aws_forwarder"},
		"DD-EVP-ORIGIN-VERSION": []string{version.Forwarder},
		"Content-Type":          []string{"application/json"},
	}

	if cfg.StepFunctionsTraceEnabled {
		header.Add("DD-STEP-FUNCTIONS-TRACE-ENABLED", "true")
	}

	return &Forwarder{
		cfg:     cfg,
		client:  client,
		storage: store,
		gzipPool: &sync.Pool{
			New: func() any {
				w, _ := gzip.NewWriterLevel(nil, cfg.CompressionLevel)
				return w
			},
		},
		header: header,
	}
}

func (f *Forwarder) Start(
	ctx context.Context,
	in <-chan json.RawMessage,
	storageTag string,
	delivery Delivery,
) error {
	if delivery == ToStorage && f.storage == nil {
		return errors.New("no failed event storage configured")
	}

	eg, ctx := errgroup.WithContext(ctx)
	eg.SetLimit(1 + httpclient.MaxConcurrency)

	batches := make(chan json.RawMessage, maxBatchesInMemory)
	eg.Go(func() error {
		defer close(batches)
		if err := batcher.New(maxLogSize, maxBatchSize, maxLogsPerBatch).Start(ctx, in, batches); err != nil {
			return fmt.Errorf("batch: %w", err)
		}
		return nil
	})

	var (
		sendErr    firstError
		storeErr   firstError
		skipIntake atomic.Bool
		stored     atomic.Bool
	)
	skipIntake.Store(delivery == ToStorage)

	for range httpclient.MaxConcurrency {
		eg.Go(func() error {
			for {
				batch, ok, _ := concurrent.SafeReader(ctx, batches)
				if !ok {
					return nil
				}

				if !skipIntake.Load() {
					err := f.send(ctx, batch, storageTag, false)
					if err == nil {
						continue
					}

					sendErr.set(err)
					skipIntake.Store(true)

					if isPermanent(err) {
						continue
					}
				}

				if f.storage == nil {
					continue
				}

				slog.DebugContext(ctx, "storing batch for retry", slog.Int("batch_bytes", len(batch)))
				if err := f.storage.Store(ctx, storage.Batch{Data: batch, StorageTag: storageTag}); err != nil {
					storeErr.set(fmt.Errorf("store: %w", err))

					continue
				}
				stored.Store(true)
			}
		})
	}

	if err := eg.Wait(); err != nil {
		return errors.Join(err, sendErr.load(), storeErr.load())
	}

	send, store := sendErr.load(), storeErr.load()
	if send == nil && store == nil {
		return nil
	}

	return &SendError{
		Err:       errors.Join(send, store),
		Stored:    store == nil && stored.Load(),
		Permanent: isPermanent(send),
	}
}

func (f *Forwarder) Retry(ctx context.Context) error {
	if f.storage == nil {
		return nil
	}

	eg, ctx := errgroup.WithContext(ctx)
	eg.SetLimit(1 + httpclient.MaxConcurrency)

	var (
		drainErr firstError
		stop     atomic.Bool
	)

	batches := make(chan storage.Batch)
	eg.Go(func() error {
		defer close(batches)

		deadline, hasDeadline := ctx.Deadline()
		for batch, err := range f.storage.Fetch(ctx) {
			if err != nil {
				return fmt.Errorf("fetch: %w", err)
			}

			if stop.Load() {
				return nil
			}

			if hasDeadline && time.Until(deadline) < retryReserve {
				slog.WarnContext(ctx, "retry drain stopped, not enough time left in the invocation",
					slog.Duration("remaining", time.Until(deadline)),
				)

				return nil
			}

			if err := concurrent.SafeSender(ctx, batches, batch); err != nil {
				return nil
			}
		}

		return nil
	})

	for range httpclient.MaxConcurrency {
		eg.Go(func() error {
			for {
				batch, ok, _ := concurrent.SafeReader(ctx, batches)
				if !ok {
					return nil
				}

				if stop.Load() {
					continue
				}

				slog.DebugContext(ctx, "retrying stored batch", slog.Int("batch_bytes", len(batch.Data)))
				if err := f.send(ctx, batch.Data, batch.StorageTag, true); err != nil {
					if !isPermanent(err) {
						drainErr.set(fmt.Errorf("send: %w", err))
						stop.Store(true)

						continue
					}

					slog.ErrorContext(ctx, "stored batch dropped, rejected by the intake",
						slog.String("key", batch.DeleteKey),
						slog.Int("batch_bytes", len(batch.Data)),
						slog.Any("error", err),
					)
				}

				if err := f.storage.Delete(ctx, batch); err != nil {
					drainErr.set(fmt.Errorf("delete: %w", err))
				}
			}
		})
	}

	if err := eg.Wait(); err != nil {
		return errors.Join(err, drainErr.load())
	}

	return drainErr.load()
}

func (f *Forwarder) send(ctx context.Context, payload json.RawMessage, storageTag string, retry bool) error {
	ctx, cancel := context.WithTimeout(ctx, httpclient.RequestTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, f.cfg.IntakeURL, bytes.NewReader(payload))
	if err != nil {
		return err
	}

	header := f.header.Clone()
	if storageTag != "" {
		header[storageTagHeader] = []string{storageTag}
	}
	if retry {
		header[ddRetryHeader] = []string{"true"}
	}
	req.Header = header

	if f.cfg.CompressionLevel != gzip.NoCompression {
		compressed, err := f.compress(payload)
		if err != nil {
			return fmt.Errorf("compress: %w", err)
		}

		slog.DebugContext(
			ctx, "sending batch to intake",
			slog.Int("original_bytes", len(payload)),
			slog.Int("compressed_bytes", len(compressed)),
		)
		req.Body = io.NopCloser(bytes.NewReader(compressed))
		req.ContentLength = int64(len(compressed))
		req.GetBody = func() (io.ReadCloser, error) {
			return io.NopCloser(bytes.NewReader(compressed)), nil
		}
		req.Header.Set("Content-Encoding", "gzip")
	}

	resp, err := f.client.Do(req)
	if err != nil {
		return fmt.Errorf("intake: %w", err)
	}
	defer httpclient.DrainClose(resp)

	if resp.StatusCode != http.StatusAccepted {
		body, _ := io.ReadAll(resp.Body)
		return &intakeError{status: resp.StatusCode, body: string(body)}
	}

	return nil
}

func (f *Forwarder) compress(payload json.RawMessage) (json.RawMessage, error) {
	buf := bufPool.Get().(*bytes.Buffer)
	gz := f.gzipPool.Get().(*gzip.Writer)
	defer bufPool.Put(buf)
	defer f.gzipPool.Put(gz)

	buf.Reset()
	gz.Reset(buf)

	if _, err := gz.Write(payload); err != nil {
		return nil, err
	}
	if err := gz.Close(); err != nil {
		return nil, err
	}

	out := bytes.Clone(buf.Bytes())
	return out, nil
}
