// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"bytes"
	"compress/gzip"
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
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storing"
	"golang.org/x/sync/errgroup"
)

var bufPool = sync.Pool{
	New: func() any { return new(bytes.Buffer) },
}

type Forwarder struct {
	cfg      *config.Config
	client   *http.Client
	storage  storing.Storage
	gzipPool *sync.Pool
	header   http.Header
}

func NewForwarder(cfg *config.Config, client *http.Client, storage storing.Storage) Forwarder {
	header := http.Header{
		"DD-API-KEY":            []string{cfg.APIKey},
		"DD-EVP-ORIGIN":         []string{"aws_forwarder"},
		"DD-EVP-ORIGIN-VERSION": []string{config.ForwarderVersion},
		"Content-Type":          []string{"application/json"},
	}

	if storage == nil {
		slog.Warn("failed event storage not configured, can lead to event loss")
	}
	return Forwarder{
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

func (f Forwarder) Start(ctx context.Context, in <-chan model.LogEntry, storageTag string) error {
	batches := make(chan []byte, httpclient.MaxConcurrency)
	batcher := batching.NewBatcher()

	producerErrCh := make(chan error, 1)
	go func() {
		defer close(batches)
		producerErrCh <- batcher.Batch(ctx, in, batches)
	}()

	var eg errgroup.Group
	eg.SetLimit(httpclient.MaxConcurrency)

	var errs []error
	var mu sync.Mutex

	for {
		body, ok, _ := concurrent.SafeReader(ctx, batches)
		if !ok {
			break
		}

		eg.Go(func() error {
			err := f.Send(ctx, body, storageTag)
			if err == nil {
				return nil
			}

			mu.Lock()
			errs = append(errs, err)
			mu.Unlock()

			if f.storage != nil {
				if storeErr := f.storage.Put(ctx, body, storageTag); storeErr != nil {
					slog.WarnContext(ctx, "failed to store batch, dropping", slog.Any("error", storeErr))
				}
			}

			return nil
		})
	}
	_ = eg.Wait()

	return errors.Join(append(errs, <-producerErrCh)...)
}

func (f Forwarder) Send(ctx context.Context, payload []byte, storageTag string) error {
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

func (f Forwarder) compress(payload []byte) ([]byte, error) {
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
