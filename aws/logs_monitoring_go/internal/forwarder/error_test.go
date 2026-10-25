// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarder

import (
	"errors"
	"fmt"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestFirstError(t *testing.T) {
	t.Parallel()

	t.Run("load is nil when unset", func(t *testing.T) {
		t.Parallel()

		var first firstError
		assert.NoError(t, first.load())
	})

	t.Run("the first writer wins", func(t *testing.T) {
		t.Parallel()

		winner := errors.New("first")

		var first firstError
		first.set(winner)
		first.set(errors.New("second"))

		assert.Equal(t, winner, first.load())
	})

	t.Run("concurrent writers keep exactly one error", func(t *testing.T) {
		t.Parallel()

		var (
			first firstError
			wg    sync.WaitGroup
		)

		for i := range 50 {
			wg.Add(1)
			go func() {
				defer wg.Done()
				first.set(fmt.Errorf("error %d", i))
			}()
		}
		wg.Wait()

		kept := first.load()
		require.Error(t, kept)
		assert.Equal(t, kept, first.load())
	})
}
