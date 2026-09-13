// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package batching

import (
	"context"
	"encoding/json"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
)

type Batcher struct {
	maxItemSize      int
	maxBatchSize     int
	maxItemsPerBatch int
	batch            []json.RawMessage
	batchSize        int
}

func New(maxItemSize, maxBatchSize, maxItemsPerBatch int) *Batcher {
	return &Batcher{
		maxItemSize:      maxItemSize,
		maxBatchSize:     maxBatchSize,
		maxItemsPerBatch: maxItemsPerBatch,
		batch:            make([]json.RawMessage, 0, maxItemsPerBatch),
		batchSize:        2, // '[' and ']'
	}
}

func (b *Batcher) Start(ctx context.Context, in <-chan json.RawMessage, out chan<- json.RawMessage) error {
	for {
		item, ok, _ := concurrent.SafeReader(ctx, in)
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

		if !b.valid(item) {
			slog.Warn(
				"invalid item, dropping",
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

func (b *Batcher) add(item json.RawMessage) bool {
	if (b.maxItemsPerBatch != 0 && len(b.batch) >= b.maxItemsPerBatch) || b.batchSize+len(item)+1 > b.maxBatchSize {
		return false
	}

	b.batch = append(b.batch, item)
	b.batchSize += len(item) + 1
	return true
}

func (b *Batcher) valid(item json.RawMessage) bool {
	return len(item) <= b.maxItemSize
}

func (b *Batcher) construct() (json.RawMessage, bool, error) {
	if len(b.batch) == 0 {
		return nil, false, nil
	}

	batch := make([]byte, 0, b.batchSize)
	batch = append(batch, '[')
	for i, item := range b.batch {
		if i > 0 {
			batch = append(batch, ',')
		}
		batch = append(batch, item...)
	}
	batch = append(batch, ']')

	slog.Debug("batch constructed", slog.Int("items", len(b.batch)), slog.Int("size_bytes", len(batch)))

	b.reset()
	return json.RawMessage(batch), true, nil
}

func (b *Batcher) reset() {
	b.batch = b.batch[:0]
	b.batchSize = 2
}
