// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storage

import (
	"context"
	"encoding/json"
	"iter"
)

const metadataStorageTagKey = "dd-storage-tag"

type Batch struct {
	Data       json.RawMessage
	StorageTag string
	DeleteKey  string
}

type Storage interface {
	Store(ctx context.Context, batch Batch) error
	Fetch(ctx context.Context) iter.Seq2[Batch, error]
	Delete(ctx context.Context, batch Batch) error
}
