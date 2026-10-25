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

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batcher"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storage"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/version"
	"golang.org/x/sync/errgroup"
)

const (
	ddRetryHeader      = "DD-RETRY-TAG"
	maxLogSize         = 1000 * 1000
	maxBatchSize       = 5 * 1000 * 1000
	maxLogsPerBatch    = 1000
	maxBatchesInMemory = 12
)

var bufPool = sync.Pool{
	New: func() any { return new(bytes.Buffer) },
}

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

func (f *Forwarder) Start(ctx context.Context, in <-chan json.RawMessage, storageTag string) error {
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
		mu        sync.Mutex
		sendErr   error
		storeErr  error
		permanent bool
		failed    atomic.Bool
	)
	for range httpclient.MaxConcurrency {
		eg.Go(func() error {
			for {
				batch, ok, _ := concurrent.SafeReader(ctx, batches)
				if !ok {
					return nil
				}

				if !failed.Load() {
					err := f.send(ctx, batch, storageTag)
					if err == nil {
						continue
					}

					mu.Lock()
					if sendErr == nil {
						sendErr = err
						permanent = isPermanent(err)
					}
					mu.Unlock()
					failed.Store(true)
				}

				if f.storage == nil {
					continue
				}

				mu.Lock()
				skipStore := permanent
				mu.Unlock()
				if skipStore {
					continue
				}

				slog.DebugContext(ctx, "send failed, storing batch for retry", slog.Int("batch_bytes", len(batch)))
				if err := f.storage.Store(ctx, storage.Batch{Data: batch, StorageTag: storageTag}); err != nil {
					mu.Lock()
					if storeErr == nil {
						storeErr = fmt.Errorf("store: %w", err)
					}
					mu.Unlock()
				}
			}
		})
	}

	if err := eg.Wait(); err != nil {
		return errors.Join(err, sendErr, storeErr)
	}
	if sendErr == nil {
		return storeErr
	}

	return &SendError{
		Err:       errors.Join(sendErr, storeErr),
		Stored:    f.storage != nil && storeErr == nil && !permanent,
		Permanent: permanent,
	}
}

func (f *Forwarder) Retry(ctx context.Context) error {
	if f.storage == nil {
		return nil
	}

	f.header.Add(ddRetryHeader, "true")
	defer func() { f.header.Del(ddRetryHeader) }()

	for batch, err := range f.storage.Fetch(ctx) {
		if err != nil {
			return fmt.Errorf("fetch: %w", err)
		}

		slog.DebugContext(ctx, "retrying stored batch", slog.Int("batch_bytes", len(batch.Data)))
		if sendErr := f.send(ctx, batch.Data, batch.StorageTag); sendErr != nil {
			return fmt.Errorf("send: %w", sendErr)
		}

		if deleteErr := f.storage.Delete(ctx, batch); deleteErr != nil {
			return fmt.Errorf("delete: %w", deleteErr)
		}
	}

	return nil
}

func (f *Forwarder) send(ctx context.Context, payload json.RawMessage, storageTag string) error {
	ctx, cancel := context.WithTimeout(ctx, httpclient.RequestTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, f.cfg.IntakeURL, bytes.NewReader(payload))
	if err != nil {
		return err
	}

	header := f.header.Clone()
	if storageTag != "" {
		header["DD-STORAGE-TAG"] = []string{storageTag}
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
