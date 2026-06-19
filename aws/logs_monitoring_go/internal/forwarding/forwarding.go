// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sync"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batching"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storing"
	"golang.org/x/sync/errgroup"
)

const (
	maxLogSize         = 1 * 1024 * 1024
	maxBatchSize       = 5 * 1024 * 1024
	maxLogsPerBatch    = 1000
	maxBatchesInMemory = 12 // 12 * 5MiB = 60MiB maximum
)

var bufPool = sync.Pool{
	New: func() any { return new(bytes.Buffer) },
}

type Forwarder struct {
	cfg      Config
	client   *http.Client
	storage  storing.Storage
	gzipPool *sync.Pool
	header   http.Header
}

type Config struct {
	APIKey           string
	IntakeURL        string
	CompressionLevel int
}

func NewForwarder(cfg Config, client *http.Client, storage storing.Storage) *Forwarder {
	header := http.Header{
		"DD-API-KEY":            []string{cfg.APIKey},
		"DD-EVP-ORIGIN":         []string{"aws_forwarder"},
		"DD-EVP-ORIGIN-VERSION": []string{config.ForwarderVersion},
		"Content-Type":          []string{"application/json"},
	}

	return &Forwarder{
		cfg:     cfg,
		client:  client,
		storage: storage,
		gzipPool: &sync.Pool{
			New: func() any {
				w, _ := gzip.NewWriterLevel(nil, cfg.CompressionLevel)
				return w
			},
		},
		header: header,
	}
}

func (f *Forwarder) Start(ctx context.Context, in <-chan model.LogEntry, storageTag string) error {
	eg, ctx := errgroup.WithContext(ctx)
	eg.SetLimit(1 + httpclient.MaxConcurrency)

	batches := make(chan json.RawMessage, maxBatchesInMemory)
	eg.Go(func() error {
		defer close(batches)
		cfg := batching.NewConfig(maxLogSize, maxBatchSize, maxLogsPerBatch)
		if err := batching.New[model.LogEntry](cfg).Start(ctx, in, batches); err != nil {
			return fmt.Errorf("batch: %w", err)
		}
		return nil
	})

	var sentErr error
	var onceSent sync.Once
	for range httpclient.MaxConcurrency {
		eg.Go(func() error {
			for {
				batch, ok, _ := concurrent.SafeReader(ctx, batches)
				if !ok {
					break
				}

				if sentErr == nil {
					err := f.send(ctx, batch, storageTag)
					if err == nil {
						continue
					}

					onceSent.Do(func() { sentErr = err })
				}

				if f.storage == nil {
					break
				}

				if err := f.storage.Store(ctx, storing.Batch{Data: batch, StorageTag: storageTag}); err != nil {
					return fmt.Errorf("store: %w", err)
				}
			}
			return nil
		})
	}

	return errors.Join(eg.Wait(), sentErr)
}

func (f *Forwarder) Retry(ctx context.Context) error {
	if f.storage == nil {
		return nil
	}

	for storedBatch, err := range f.storage.Fetch(ctx) {
		if err != nil {
			return fmt.Errorf("fetch: %w", err)
		}

		if sendErr := f.send(ctx, storedBatch.Data, storedBatch.StorageTag); sendErr != nil {
			return fmt.Errorf("send: %w", sendErr)
		}

		if deleteErr := f.storage.Delete(ctx, storedBatch); deleteErr != nil {
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
		if len(body) > 0 {
			return fmt.Errorf("intake (http/%d): %s", resp.StatusCode, string(body))
		}
		return fmt.Errorf("intake (http/%d)", resp.StatusCode)
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
