// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"errors"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestEphemeralAPIKeySource_Get(t *testing.T) {
	t.Parallel()

	var keyBefore, keyAfter APIKey = "key-1", "key-2"

	tests := map[string]struct {
		delay           time.Duration
		refreshInterval time.Duration
		wantBefore      APIKey
		wantAfter       APIKey
	}{
		"double get within refresh interval provide same key": {
			delay:           time.Hour,
			refreshInterval: time.Hour + time.Nanosecond,
			wantBefore:      keyBefore,
			wantAfter:       keyBefore,
		},
		"get after refresh interval provide different keys": {
			delay:           time.Hour,
			refreshInterval: time.Hour - time.Nanosecond,
			wantBefore:      keyBefore,
			wantAfter:       keyAfter,
		},
		"get exactly at the refresh interval provide different keys": {
			delay:           time.Hour,
			refreshInterval: time.Hour,
			wantBefore:      keyBefore,
			wantAfter:       keyAfter,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				source := &fakeAPIKeySource{fn: fakeBeforeAfterAPIKeySource(tc.delay, keyBefore, keyAfter)}
				ks := NewEphemeralAPIKeySource(source, tc.refreshInterval)

				key1, err := ks.Get(t.Context())
				require.NoError(t, err)
				synctest.Sleep(tc.delay)
				key2, err := ks.Get(t.Context())
				require.NoError(t, err)

				assert.Equal(t, tc.wantBefore, key1)
				assert.Equal(t, tc.wantAfter, key2)
			})
		})
	}

	t.Run("get fails without previous success", func(t *testing.T) {
		t.Parallel()

		source := &fakeAPIKeySource{fn: fakeFailure}
		ks := NewEphemeralAPIKeySource(source, time.Hour)

		_, err := ks.Get(t.Context())
		require.Error(t, err)
		assert.Equal(t, 1, ks.failures)
	})

	t.Run("get serves previous key when it fails", func(t *testing.T) {
		t.Parallel()

		source := &fakeAPIKeySource{fn: fakeSucceedsThenFailsAPIKeySource("key")}
		ks := NewEphemeralAPIKeySource(source, time.Hour)

		key1, err := ks.Get(t.Context())
		require.NoError(t, err)
		assert.Equal(t, 0, ks.failures)

		ks.Invalidate()

		key2, err := ks.Get(t.Context())
		require.NoError(t, err)
		assert.Equal(t, key1, key2)
		assert.Equal(t, 1, ks.failures)
	})

	t.Run("failures accumulate then reset on success", func(t *testing.T) {
		t.Parallel()

		var calls int
		source := &fakeAPIKeySource{fn: func(context.Context) (APIKey, error) {
			calls++
			if calls <= 2 {
				return "", errors.New("")
			}
			return "key", nil
		}}
		ks := NewEphemeralAPIKeySource(source, time.Hour)

		_, err := ks.Get(t.Context())
		require.Error(t, err)
		assert.Equal(t, 1, ks.failures)

		ks.Invalidate()
		_, err = ks.Get(t.Context())
		require.Error(t, err)
		assert.Equal(t, 2, ks.failures)

		ks.Invalidate()
		key, err := ks.Get(t.Context())
		require.NoError(t, err)
		assert.Equal(t, APIKey("key"), key)
		assert.Equal(t, 0, ks.failures)
	})

	t.Run("concurrent calls on expiry fetch once", func(t *testing.T) {
		t.Parallel()

		source := &fakeAPIKeySource{fn: fakeSuccess}
		ks := NewEphemeralAPIKeySource(source, time.Hour)

		var wg sync.WaitGroup
		for range 50 {
			wg.Add(1)
			go func() {
				defer wg.Done()
				_, _ = ks.Get(t.Context())
			}()
		}
		wg.Wait()

		assert.Equal(t, int32(1), source.calls.Load())
	})

	t.Run("invalidate forces immediate get", func(t *testing.T) {
		t.Parallel()

		source := &fakeAPIKeySource{fn: fakeSuccess}
		ks := NewEphemeralAPIKeySource(source, time.Nanosecond)

		_, err := ks.Get(t.Context())
		require.NoError(t, err)

		ks.Invalidate()

		_, err = ks.Get(t.Context())
		require.NoError(t, err)

		assert.Equal(t, int32(2), source.calls.Load())
	})
}

func TestNextBackoff(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		base     time.Duration
		failures int
		want     time.Duration
	}{
		"no failures": {
			base:     time.Minute,
			failures: 0,
			want:     time.Minute,
		},
		"one failure doubles": {
			base:     time.Minute,
			failures: 1,
			want:     2 * time.Minute,
		},
		"two failures quadruples": {
			base:     time.Minute,
			failures: 2,
			want:     4 * time.Minute,
		},
		"large failure count caps at maxBackoff": {
			base:     time.Minute,
			failures: 1000,
			want:     maxBackoff,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			got := nextBackoff(tc.base, tc.failures)

			low := time.Duration(float64(tc.want) * (1 - backoffJitter))
			high := time.Duration(float64(tc.want) * (1 + backoffJitter))
			assert.GreaterOrEqual(t, got, low)
			assert.LessOrEqual(t, got, high)
		})
	}
}
