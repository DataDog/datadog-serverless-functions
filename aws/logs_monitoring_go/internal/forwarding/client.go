// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"net"
	"net/http"
	"time"
)

const (
	dialContextTimeout  = 500 * time.Millisecond
	tlsHandshakeTimeout = 1 * time.Second
	timeout             = 5 * time.Second
	defaultMaxAttempts  = 3
)

var Client *http.Client

func init() {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSHandshakeTimeout = tlsHandshakeTimeout
	transport.DialContext = (&net.Dialer{
		Timeout: dialContextTimeout,
	}).DialContext
	Client = &http.Client{
		Timeout: timeout,
		Transport: WithCompression(
			WithRetry(defaultMaxAttempts,
				transport,
			),
		),
	}
}
