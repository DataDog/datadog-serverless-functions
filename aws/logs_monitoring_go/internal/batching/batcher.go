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
)

type Config struct {
	maxItemSize      int
	maxBatchSize     int
	maxItemsPerBatch int
}

func NewConfig(maxItemSize, maxBatchSize, maxItemsPerBatch int) Config {
	return Config{
		maxItemSize:      maxItemSize,
		maxBatchSize:     maxBatchSize,
		maxItemsPerBatch: maxItemsPerBatch,
	}
}

type Batcher[T any] struct {
	Config
	batch     []json.RawMessage
	batchSize int
}

func New[T any](cfg Config) *Batcher[T] {
	return &Batcher[T]{
		Config:    cfg,
		batch:     make([]json.RawMessage, 0, cfg.maxItemsPerBatch),
		batchSize: 2, // '[' and ']'
	}
}

func (b *Batcher[T]) Start(ctx context.Context, in <-chan T, out chan<- json.RawMessage) error {
	for {
		v, ok, _ := concurrent.SafeReader(ctx, in)
		if !ok {
			batch, constructed, err := b.construct()
			if err != nil {
				return err
			}

			if constructed {
				if err = concurrent.SafeSender(ctx, out, batch); err != nil {
					return err
				}
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
			batch, constructed, err := b.construct()
			if err != nil {
				return err
			}
			_ = b.add(item)

			if !constructed {
				continue
			}

			if err = concurrent.SafeSender(ctx, out, batch); err != nil {
				return err
			}
		}
	}
	return nil
}

func (b *Batcher[T]) add(item json.RawMessage) bool {
	if (b.maxItemsPerBatch != 0 && len(b.batch) >= b.maxItemsPerBatch) || b.batchSize+len(item)+1 > b.maxBatchSize {
		return false
	}

	b.batch = append(b.batch, item)
	b.batchSize += len(item) + 1
	return true
}

func (b *Batcher[T]) valid(item json.RawMessage) bool {
	return len(item) <= b.maxItemSize
}

func (b *Batcher[T]) construct() (json.RawMessage, bool, error) {
	if len(b.batch) == 0 {
		return nil, false, nil
	}

	batch, err := json.Marshal(&b.batch)
	if err != nil {
		return nil, false, fmt.Errorf("marshal: %w", err)
	}

	b.reset()
	return json.RawMessage(batch), true, nil
}

func (b *Batcher[T]) reset() {
	b.batch = b.batch[:0]
	b.batchSize = 2
}
