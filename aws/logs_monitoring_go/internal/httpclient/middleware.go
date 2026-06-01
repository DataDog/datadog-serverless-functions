// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package httpclient

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
	"sync/atomic"
	"time"

	"github.com/aws/aws-lambda-go/lambdacontext"
)

var requestSeq atomic.Int64

type RoundTripperFunc func(*http.Request) (*http.Response, error)

func (f RoundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func WithRetry(maxAttempts int, next http.RoundTripper) RoundTripperFunc {
	return func(req *http.Request) (*http.Response, error) {
		id := requestSeq.Add(1)

		var resp *http.Response
		var err error

		for attempt := range maxAttempts {
			if attempt > 0 && req.GetBody != nil {
				req.Body, err = req.GetBody()
				if err != nil {
					return nil, fmt.Errorf("resetting request body: %w", err)
				}
			}

			start := time.Now()
			resp, err = next.RoundTrip(req)

			attrs := []slog.Attr{
				slog.Int64("request_id", id),
				slog.Int("attempt", attempt+1),
				slog.Duration("duration", time.Since(start)),
			}
			if lc, ok := lambdacontext.FromContext(req.Context()); ok {
				attrs = append(attrs, slog.String("aws_request_id", lc.AwsRequestID))
			}

			if err != nil {
				slog.LogAttrs(req.Context(), slog.LevelWarn, "request failed", append(attrs, slog.String("error", err.Error()))...)
				if attempt < maxAttempts-1 {
					backoff(req.Context(), attempt)
				}
				continue
			}

			attrs = append(attrs, slog.Int("status", resp.StatusCode))

			if isRetryable(resp.StatusCode) && attempt < maxAttempts-1 {
				slog.LogAttrs(req.Context(), slog.LevelWarn, "retryable response", attrs...)
				DrainClose(resp)
				backoff(req.Context(), attempt)
				continue
			}

			slog.LogAttrs(req.Context(), slog.LevelDebug, "request complete", attrs...)
			return resp, nil
		}

		return resp, err
	}
}

func isRetryable(statusCode int) bool {
	switch statusCode {
	case http.StatusTooManyRequests,
		http.StatusRequestTimeout,
		http.StatusInternalServerError,
		http.StatusGatewayTimeout,
		http.StatusServiceUnavailable:
		return true
	default:
		return false
	}
}

func backoff(ctx context.Context, attempt int) {
	select {
	case <-ctx.Done():
		return
	default:
	}

	duration := time.Duration(1<<attempt) * 500 * time.Millisecond // 500ms, 1s, 2s
	select {
	case <-time.After(duration):
	case <-ctx.Done():
	}
}
