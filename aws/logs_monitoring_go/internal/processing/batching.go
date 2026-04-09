// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package processing

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
)

const (
	maxItemSize      = 1 * 1024 * 1024
	maxBatchSize     = 5 * 1024 * 1024
	maxItemsPerBatch = 1000
)

type Batcher[T any] struct {
	batch     [][]byte
	batchSize int
	in        <-chan T
	out       chan<- []byte
}

func NewBatcher[T any](in <-chan T, out chan<- []byte) *Batcher[T] {
	return &Batcher[T]{
		batch: make([][]byte, 0, maxItemsPerBatch),
		in:    in,
		out:   out,
	}
}

func (b *Batcher[T]) Batch(ctx context.Context) error {
	for {
		entry, ok, err := concurrent.SafeReader(ctx, b.in)
		if err != nil {
			return err
		}
		if !ok {
			return b.flush(ctx)
		}

		data, err := json.Marshal(entry)
		if err != nil {
			slog.Warn("failed to marshal log entry, skipped", slog.Any("error", err))
			continue
		}

		if len(data) > maxItemSize {
			slog.Warn("log entry exceeds max item size, dropping",
				slog.Int("size", len(data)),
				slog.Int("max", maxItemSize),
			)
			continue
		}

		if b.batchSize+len(data) > maxBatchSize || len(b.batch) >= maxItemsPerBatch {
			if err := b.flush(ctx); err != nil {
				return err
			}
		}

		b.batch = append(b.batch, data)
		b.batchSize += len(data)
	}
}

func (b *Batcher[T]) flush(ctx context.Context) error {
	if len(b.batch) == 0 {
		return nil
	}

	payload := assembleBatch(b.batch)
	b.batch = b.batch[:0]
	b.batchSize = 0

	return concurrent.SafeSender(ctx, b.out, payload)
}

func assembleBatch(entries [][]byte) []byte {
	var buf bytes.Buffer

	buf.WriteByte('[')
	for i, entry := range entries {
		if i > 0 {
			buf.WriteByte(',')
		}
		buf.Write(entry)
	}
	buf.WriteByte(']')

	return buf.Bytes()
}
