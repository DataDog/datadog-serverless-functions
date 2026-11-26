// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"errors"
	"sync/atomic"
	"time"
)

func fakeSuccess(context.Context) (APIKey, error) { return "", nil }

func fakeFailure(context.Context) (APIKey, error) { return "", errors.New("") }

type fakeAPIKeySource struct {
	calls atomic.Int32
	fn    func(context.Context) (APIKey, error)
}

func (f *fakeAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	f.calls.Add(1)
	return f.fn(ctx)
}

type fakeInvalidatableAPIKeySource struct {
	APIKeySource
	invalidateCalls atomic.Int32
}

func (f *fakeInvalidatableAPIKeySource) Invalidate() {
	f.invalidateCalls.Add(1)
}

func fakeBeforeAfterAPIKeySource(delay time.Duration, before, after APIKey) func(context.Context) (APIKey, error) {
	now := time.Now()
	return func(context.Context) (APIKey, error) {
		if time.Now().Before(now.Add(delay)) {
			return before, nil
		}
		return after, nil
	}
}

func fakeSucceedsThenFailsAPIKeySource(key APIKey) func(context.Context) (APIKey, error) {
	var called bool
	return func(context.Context) (APIKey, error) {
		if !called {
			called = true
			return key, nil
		}
		return "", errors.New("")
	}
}
