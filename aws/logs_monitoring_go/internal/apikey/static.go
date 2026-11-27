// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"sync"
)

type StaticAPIKeySource struct {
	Source APIKeySource

	once sync.Once
	key  APIKey
	err  error
}

func (ks *StaticAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	ks.once.Do(func() {
		ks.key, ks.err = ks.Source.Get(ctx)
	})
	return ks.key, ks.err
}
