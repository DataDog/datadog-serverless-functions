// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package httpclient

import (
	"io"
	"log/slog"
	"net"
	"net/http"
	"time"
)

const (
	dialContextTimeout   = 1 * time.Second
	dialContextKeepAlive = 60 * time.Second
	tlsHandshakeTimeout  = 2 * time.Second
	RequestTimeout       = 7 * time.Second
	DefaultMaxAttempts   = 3
	MaxConcurrency       = 5
)

var Client *http.Client

func Init(opts ...TLSOption) {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSHandshakeTimeout = tlsHandshakeTimeout
	transport.MaxIdleConnsPerHost = MaxConcurrency
	transport.DialContext = (&net.Dialer{
		Timeout:   dialContextTimeout,
		KeepAlive: dialContextKeepAlive,
	}).DialContext

	for _, opt := range opts {
		opt(transport.TLSClientConfig)
	}

	Client = &http.Client{Transport: WithRetry(DefaultMaxAttempts, transport)}
}

func DrainClose(resp *http.Response) {
	if _, err := io.Copy(io.Discard, resp.Body); err != nil {
		slog.Warn("draining response body", slog.Any("error", err))
	}
	if err := resp.Body.Close(); err != nil {
		slog.Warn("closing response body", slog.Any("error", err))
	}
}
