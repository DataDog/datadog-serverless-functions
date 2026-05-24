// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"bytes"
	"compress/gzip"
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"sync/atomic"
	"time"
)

var requestSeq atomic.Int64

type RoundTripperFunc func(*http.Request) (*http.Response, error)

func (f RoundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func WithCompression(next http.RoundTripper) RoundTripperFunc {
	return func(req *http.Request) (*http.Response, error) {
		var buf bytes.Buffer
		gz := gzip.NewWriter(&buf)
		if _, err := io.Copy(gz, req.Body); err != nil {
			return nil, fmt.Errorf("compress: %w", err)
		}
		if err := gz.Close(); err != nil {
			return nil, fmt.Errorf("close: %w", err)
		}

		compressed := buf.Bytes()
		req.Body = io.NopCloser(bytes.NewReader(compressed))
		req.ContentLength = int64(len(compressed))
		req.GetBody = func() (io.ReadCloser, error) {
			return io.NopCloser(bytes.NewReader(compressed)), nil
		}
		req.Header.Set("Content-Encoding", "gzip")

		return next.RoundTrip(req)
	}
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

			if err != nil {
				slog.LogAttrs(req.Context(), slog.LevelWarn, "request failed", append(attrs, slog.String("error", err.Error()))...)
				continue
			}

			attrs = append(attrs, slog.Int("status", resp.StatusCode))

			if !isRetryable(resp.StatusCode) {
				slog.LogAttrs(req.Context(), slog.LevelDebug, "request complete", attrs...)
				return resp, nil
			}

			slog.LogAttrs(req.Context(), slog.LevelWarn, "retryable response", attrs...)
			drainClose(resp)

			if attempt < maxAttempts-1 {
				backoff(req.Context(), attempt)
			}
		}

		return resp, err
	}
}

func isRetryable(statusCode int) bool {
	switch statusCode {
	case http.StatusTooManyRequests,
		http.StatusRequestTimeout,
		http.StatusInternalServerError,
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

	duration := time.Duration(1<<attempt) * 50 * time.Millisecond // 50ms, 100ms, 200ms
	select {
	case <-time.After(duration):
	case <-ctx.Done():
	}
}
