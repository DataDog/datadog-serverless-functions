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
	"sync"
	"sync/atomic"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batching"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storing"
	"golang.org/x/sync/errgroup"
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

	batches := make(chan []byte)
	eg.Go(func() error {
		defer close(batches)
		if err := batching.New().Batch(ctx, in, batches); err != nil {
			return fmt.Errorf("batch: %w", err)
		}
		return nil
	})

	var stopSending atomic.Bool
	for range httpclient.MaxConcurrency {
		eg.Go(func() error {
			var sendingErr error
			for {
				batch, ok, _ := concurrent.SafeReader(ctx, batches)
				if !ok {
					break
				}

				if !stopSending.Load() {
					sendingErr = f.send(ctx, batch, storageTag)
					if sendingErr == nil {
						continue
					}

					stopSending.Store(true)
					slog.WarnContext(ctx, "failed to send batch", slog.Any("error", sendingErr))
				}

				if err := f.store(ctx, batch, storageTag); err != nil {
					return fmt.Errorf("store: %w", err)
				}
			}

			return sendingErr
		})
	}

	return eg.Wait()
}

func (f *Forwarder) store(ctx context.Context, batch []byte, storageTag string) error {
	if f.storage == nil {
		return nil
	}

	if err := f.storage.Put(ctx, batch, storageTag); err != nil {
		return fmt.Errorf("put: %w", err)
	}

	return nil
}

func (f *Forwarder) Retry(ctx context.Context) error {
	keys, listErr := f.storage.List(ctx)
	if listErr != nil {
		return fmt.Errorf("list: %w", listErr)
	}

	slog.InfoContext(ctx, "retrying stored batches", slog.Int("count", len(keys)))
	for _, key := range keys {
		payload, storageTag, getErr := f.storage.Get(ctx, key)
		if getErr != nil {
			return fmt.Errorf("list: %w", getErr)
		}

		if sendErr := f.send(ctx, payload, storageTag); sendErr != nil {
			return fmt.Errorf("send: %w", sendErr)
		}

		if deleteErr := f.storage.Delete(ctx, key); deleteErr != nil {
			return fmt.Errorf("delete: %w", deleteErr)
		}

		slog.DebugContext(ctx, "batch sent successfully", slog.String("key", key))
	}

	return nil
}

func (f *Forwarder) send(ctx context.Context, payload []byte, storageTag string) error {
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

func (f *Forwarder) compress(payload []byte) ([]byte, error) {
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
