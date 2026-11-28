// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import "context"

type MultiAPIKeySource struct {
	Primary, Secondary APIKeySource
}

func (ks MultiAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	if key, err := ks.Primary.Get(ctx); err == nil {
		return key, nil
	}
	return ks.Secondary.Get(ctx)
}
