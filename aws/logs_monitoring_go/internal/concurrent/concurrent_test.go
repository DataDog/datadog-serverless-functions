// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package concurrent

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSafeSender(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		setup    func() (context.Context, chan string, func())
		instance string
		wantErr  bool
	}{
		"send succeeds on buffered channel": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithCancel(context.Background())
				ch := make(chan string, 1)
				return ctx, ch, cancel
			},
			instance: "hello",
			wantErr:  false,
		},
		"returns error when context is already canceled": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithCancel(context.Background())
				cancel()
				ch := make(chan string)
				return ctx, ch, cancel
			},
			instance: "hello",
			wantErr:  true,
		},
		"returns error when context is canceled while blocking": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithCancel(context.Background())
				ch := make(chan string)
				go func() {
					time.Sleep(100 * time.Millisecond)
					cancel()
				}()
				return ctx, ch, cancel
			},
			instance: "hello",
			wantErr:  true,
		},
		"returns error when context deadline exceeds while blocking": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
				ch := make(chan string)
				return ctx, ch, cancel
			},
			instance: "hello",
			wantErr:  true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx, ch, cancel := tc.setup()
			defer cancel()

			err := SafeSender(ctx, ch, tc.instance)

			if tc.wantErr {
				require.Error(t, err)
				return
			}

			require.NoError(t, err)
			received := <-ch
			assert.Equal(t, tc.instance, received)
		})
	}
}

func TestSafeReader(t *testing.T) {
	t.Parallel()

	type want struct {
		val string
		ok  bool
		err bool
	}

	tests := map[string]struct {
		setup func() (context.Context, chan string, func())
		want  want
	}{
		"read succeeds when value is available": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithCancel(context.Background())
				ch := make(chan string, 1)
				ch <- "hello"
				return ctx, ch, cancel
			},
			want: want{val: "hello", ok: true},
		},
		"returns zero value and false when channel is closed": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithCancel(context.Background())
				ch := make(chan string)
				close(ch)
				return ctx, ch, cancel
			},
		},
		"returns error when context is already canceled": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithCancel(context.Background())
				cancel()
				ch := make(chan string)
				return ctx, ch, cancel
			},
			want: want{err: true},
		},
		"returns error when context is canceled while blocking": {
			setup: func() (context.Context, chan string, func()) {
				ctx, cancel := context.WithCancel(context.Background())
				ch := make(chan string)
				go func() {
					time.Sleep(100 * time.Millisecond)
					cancel()
				}()
				return ctx, ch, cancel
			},
			want: want{err: true},
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx, ch, cancel := tc.setup()
			defer cancel()

			val, ok, err := SafeReader(ctx, ch)

			if tc.want.err {
				require.Error(t, err)
				return
			}

			require.NoError(t, err)
			assert.Equal(t, tc.want.ok, ok)
			assert.Equal(t, tc.want.val, val)
		})
	}
}
