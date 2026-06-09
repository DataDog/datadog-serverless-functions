// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package batching

type Option func(*Batcher)

func WithMaxItemSize(n int) Option {
	return func(b *Batcher) {
		b.maxItemSize = n
	}
}

func WithMaxBatchSize(n int) Option {
	return func(b *Batcher) {
		b.maxBatchSize = n
	}
}

func WithMaxItemsPerBatch(n int) Option {
	return func(b *Batcher) {
		b.maxItemsPerBatch = n
	}
}
