// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package batching

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

const (
	defaultMaxItemSize      = 1 * 1024 * 1024
	defaultMaxBatchSize     = 5 * 1024 * 1024
	defaultMaxItemsPerBatch = 1000
)

type Batcher struct {
	maxItemSize      int
	maxBatchSize     int
	maxItemsPerBatch int
	batch            []json.RawMessage
	batchSize        int
}

func New(opts ...Option) *Batcher {
	b := &Batcher{
		maxItemSize:      defaultMaxItemSize,
		maxBatchSize:     defaultMaxBatchSize,
		maxItemsPerBatch: defaultMaxItemsPerBatch,
		batchSize:        2, // '[' and ']'
	}

	for _, opt := range opts {
		opt(b)
	}

	b.batch = make([]json.RawMessage, 0, b.maxItemsPerBatch)
	return b
}

func (b *Batcher) Start(ctx context.Context, in <-chan model.LogEntry, out chan<- json.RawMessage) error {
	for {
		v, ok, _ := concurrent.SafeReader(ctx, in)
		if !ok {
			batch, err := b.construct()
			if err != nil {
				return err
			}
			if err = concurrent.SafeSender(ctx, out, batch); err != nil {
				return err
			}
			break
		}

		item, err := json.Marshal(v)
		if err != nil {
			return fmt.Errorf("marshal: %w", err)
		}

		if !b.valid(item) {
			slog.Warn("invalid item, dropping",
				slog.Int("size", len(item)),
				slog.Int("max", b.maxItemSize),
			)
			continue
		}

		if ok := b.add(item); !ok {
			batch, err := b.construct()
			if err != nil {
				return err
			}
			if err = concurrent.SafeSender(ctx, out, batch); err != nil {
				return err
			}
			_ = b.add(item)
		}
	}
	return nil
}

func (b *Batcher) StartSlice(items []json.RawMessage) ([]json.RawMessage, error) {
	var batchedItems []json.RawMessage
	for _, item := range items {
		if !b.valid(item) {
			slog.Warn("invalid item, dropping",
				slog.Int("size", len(item)),
				slog.Int("max", b.maxItemSize),
			)
			continue
		}

		if ok := b.add(item); !ok {
			batch, err := b.construct()
			if err != nil {
				return nil, err
			}
			batchedItems = append(batchedItems, batch)
			_ = b.add(item)
		}
	}

	batch, err := b.construct()
	if err != nil {
		return nil, err
	}

	if batch != nil {
		batchedItems = append(batchedItems, batch)
	}
	return batchedItems, nil
}

func (b *Batcher) add(item json.RawMessage) bool {
	if len(b.batch) >= b.maxItemsPerBatch || b.batchSize+len(item)+1 > b.maxBatchSize {
		return false
	}

	b.batch = append(b.batch, item)
	b.batchSize += len(item) + 1 // ','
	return true
}

func (b *Batcher) valid(item json.RawMessage) bool {
	return len(item) <= b.maxItemSize
}

func (b *Batcher) construct() (json.RawMessage, error) {
	if len(b.batch) == 0 {
		return nil, nil
	}

	batch, err := json.Marshal(&b.batch)
	if err != nil {
		return nil, fmt.Errorf("marshal: %w", err)
	}

	b.reset()
	return json.RawMessage(batch), nil
}

func (b *Batcher) reset() {
	b.batch = b.batch[:0]
	b.batchSize = 2
}
