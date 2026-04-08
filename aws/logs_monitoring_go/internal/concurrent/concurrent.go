// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package concurrent

import "context"

func SafeSender[T any](ctx context.Context, ch chan<- T, instance T) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	select {
	case <-ctx.Done():
		return ctx.Err()
	case ch <- instance:
		return nil
	}
}

func SafeReader[T any](ctx context.Context, ch <-chan T) (T, bool, error) {
	var value T

	select {
	case <-ctx.Done():
		return value, false, ctx.Err()
	default:
	}

	var ok bool

	select {
	case <-ctx.Done():
		return value, false, ctx.Err()
	case value, ok = <-ch:
		return value, ok, nil
	}
}
