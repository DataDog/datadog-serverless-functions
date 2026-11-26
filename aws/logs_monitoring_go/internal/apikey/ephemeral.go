// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"log/slog"
	"math"
	"math/rand/v2"
	"sync"
	"time"
)

const (
	maxBackoff        = time.Hour
	backoffMultiplier = 2.0
	backoffJitter     = 0.10
)

type EphemeralAPIKeySource struct {
	Source APIKeySource

	mu        sync.RWMutex
	refreshAt time.Time
	interval  time.Duration
	failures  int
	key       APIKey
	err       error
}

func NewEphemeralAPIKeySource(source APIKeySource, interval time.Duration) *EphemeralAPIKeySource {
	return &EphemeralAPIKeySource{
		Source:    source,
		refreshAt: time.Now(),
		interval:  interval,
	}
}

func (ks *EphemeralAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	ks.mu.RLock()
	if !ks.expired() {
		defer ks.mu.RUnlock()
		return ks.key, ks.err
	}
	ks.mu.RUnlock()

	ks.mu.Lock()
	defer ks.mu.Unlock()
	if !ks.expired() {
		return ks.key, ks.err
	}

	key, err := ks.Source.Get(ctx)
	if err != nil {
		ks.failures++
		wait := nextBackoff(ks.interval, ks.failures)
		ks.refreshAt = time.Now().Add(wait)

		slog.WarnContext(ctx, "get ephemeral API key", slog.Any("error", err), slog.Int("failures", ks.failures), slog.Duration("next_attempt_in", wait))
		if ks.key != "" {
			return ks.key, ks.err
		}
		return "", err
	}
	slog.DebugContext(ctx, "ephemeral API key refreshed", slog.Bool("changed", ks.key != key))

	ks.failures = 0
	ks.refreshAt = time.Now().Add(ks.interval)
	ks.key, ks.err = key, err
	return ks.key, ks.err
}

// Callers must hold ks.mu before calling
func (ks *EphemeralAPIKeySource) expired() bool {
	return !time.Now().Before(ks.refreshAt)
}

func (ks *EphemeralAPIKeySource) Invalidate() {
	ks.mu.Lock()
	defer ks.mu.Unlock()
	ks.refreshAt = time.Now()
}

func nextBackoff(base time.Duration, failures int) time.Duration {
	interval := min(
		float64(base)*math.Pow(backoffMultiplier, float64(failures)),
		float64(maxBackoff),
	)
	jitter := interval * backoffJitter * (2*rand.Float64() - 1)
	return time.Duration(interval + jitter)
}
