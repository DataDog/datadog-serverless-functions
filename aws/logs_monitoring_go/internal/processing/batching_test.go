// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package processing

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

func makeEntry(msg string) model.CloudwatchLogEntry {
	return model.CloudwatchLogEntry{
		ID:      "id1",
		Message: msg,
		Source:  "test",
		Service: "test",
		Host:    "test-host",
	}
}

func feedChannel(entries ...model.CloudwatchLogEntry) <-chan model.CloudwatchLogEntry {
	ch := make(chan model.CloudwatchLogEntry, len(entries))
	for _, e := range entries {
		ch <- e
	}
	close(ch)
	return ch
}

func collectBatches(t *testing.T, in <-chan model.CloudwatchLogEntry) [][]byte {
	t.Helper()

	out := make(chan []byte, 100)
	batcher := NewBatcher[model.CloudwatchLogEntry]()
	err := batcher.Batch(context.Background(), in, out)
	close(out)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	var batches [][]byte
	for b := range out {
		batches = append(batches, b)
	}
	return batches
}

func TestBatch_EmptyInput(t *testing.T) {
	t.Parallel()

	batches := collectBatches(t, feedChannel())
	if len(batches) != 0 {
		t.Fatalf("expected 0 batches, got %d", len(batches))
	}
}

func TestBatch_SingleEntry(t *testing.T) {
	t.Parallel()

	batches := collectBatches(t, feedChannel(makeEntry("hello")))
	if len(batches) != 1 {
		t.Fatalf("expected 1 batch, got %d", len(batches))
	}

	var entries []model.CloudwatchLogEntry
	if err := json.Unmarshal(batches[0], &entries); err != nil {
		t.Fatalf("failed to unmarshal batch: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry in batch, got %d", len(entries))
	}
	if entries[0].Message != "hello" {
		t.Errorf("expected message 'hello', got %q", entries[0].Message)
	}
}

func TestBatch_MultipleEntriesFitInOneBatch(t *testing.T) {
	t.Parallel()

	batches := collectBatches(t, feedChannel(makeEntry("one"), makeEntry("two"), makeEntry("three")))
	if len(batches) != 1 {
		t.Fatalf("expected 1 batch, got %d", len(batches))
	}

	var entries []model.CloudwatchLogEntry
	if err := json.Unmarshal(batches[0], &entries); err != nil {
		t.Fatalf("failed to unmarshal batch: %v", err)
	}
	if len(entries) != 3 {
		t.Fatalf("expected 3 entries in batch, got %d", len(entries))
	}
}

func TestBatch_OversizedEntryDropped(t *testing.T) {
	t.Parallel()

	bigMsg := strings.Repeat("x", maxItemSize+1)
	batches := collectBatches(t, feedChannel(makeEntry(bigMsg), makeEntry("small")))
	if len(batches) != 1 {
		t.Fatalf("expected 1 batch, got %d", len(batches))
	}

	var entries []model.CloudwatchLogEntry
	if err := json.Unmarshal(batches[0], &entries); err != nil {
		t.Fatalf("failed to unmarshal batch: %v", err)
	}
	if len(entries) != 1 {
		t.Fatalf("expected 1 entry (oversized dropped), got %d", len(entries))
	}
	if entries[0].Message != "small" {
		t.Errorf("expected message 'small', got %q", entries[0].Message)
	}
}

func TestBatch_SplitsOnMaxItems(t *testing.T) {
	t.Parallel()

	entries := make([]model.CloudwatchLogEntry, maxItemsPerBatch+1)
	for i := range entries {
		entries[i] = makeEntry("msg")
	}

	batches := collectBatches(t, feedChannel(entries...))
	if len(batches) != 2 {
		t.Fatalf("expected 2 batches, got %d", len(batches))
	}

	var batch1 []model.CloudwatchLogEntry
	if err := json.Unmarshal(batches[0], &batch1); err != nil {
		t.Fatalf("failed to unmarshal batch 0: %v", err)
	}
	if len(batch1) != maxItemsPerBatch {
		t.Errorf("expected %d entries in first batch, got %d", maxItemsPerBatch, len(batch1))
	}

	var batch2 []model.CloudwatchLogEntry
	if err := json.Unmarshal(batches[1], &batch2); err != nil {
		t.Fatalf("failed to unmarshal batch 1: %v", err)
	}
	if len(batch2) != 1 {
		t.Errorf("expected 1 entry in second batch, got %d", len(batch2))
	}
}

func TestBatch_SplitsOnMaxSize(t *testing.T) {
	t.Parallel()

	sample := makeEntry("")
	data, _ := json.Marshal(sample)
	overhead := len(data)

	bigMsg := strings.Repeat("a", maxItemSize-overhead)
	entriesNeeded := maxBatchSize/maxItemSize + 2
	var inputEntries []model.CloudwatchLogEntry
	for i := 0; i < entriesNeeded; i++ {
		inputEntries = append(inputEntries, makeEntry(bigMsg))
	}

	batches := collectBatches(t, feedChannel(inputEntries...))
	if len(batches) < 2 {
		t.Fatalf("expected at least 2 batches, got %d", len(batches))
	}
}

func TestBatch_ContextCancellation(t *testing.T) {
	t.Parallel()

	ctx, cancel := context.WithCancel(context.Background())
	in := make(chan model.CloudwatchLogEntry)
	out := make(chan []byte, 100)

	cancel()

	batcher := NewBatcher[model.CloudwatchLogEntry]()
	err := batcher.Batch(ctx, in, out)
	if err == nil {
		t.Fatal("expected context cancellation error")
	}
}
