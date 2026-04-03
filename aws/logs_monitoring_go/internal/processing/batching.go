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
	maxItemSize      = 512 * 1024
	maxBatchSize     = 4 * 1024 * 1024
	maxItemsPerBatch = 400
)

func Batch[T any](ctx context.Context, in <-chan T, out chan<- []byte) error {
	batch := make([][]byte, 0, maxItemsPerBatch)
	batchSize := 0

	flush := func() error {
		if len(batch) == 0 {
			return nil
		}
		payload := assembleBatch(batch)
		batch = batch[:0]
		batchSize = 0
		return concurrent.SafeSender(ctx, out, payload)
	}

	for {
		entry, ok, err := concurrent.SafeReader(ctx, in)
		if err != nil {
			return err
		}
		if !ok {
			return flush()
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

		if batchSize+len(data) > maxBatchSize || len(batch) >= maxItemsPerBatch {
			if err := flush(); err != nil {
				return err
			}
		}

		batch = append(batch, data)
		batchSize += len(data)
	}
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
