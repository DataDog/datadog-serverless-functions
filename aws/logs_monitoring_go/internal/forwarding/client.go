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
	dialContextTimeout   = 1 * time.Second
	dialContextKeepAlive = 60 * time.Second
	tlsHandshakeTimeout  = 2 * time.Second
	timeout              = 7 * time.Second
	defaultMaxAttempts   = 3
)

var Client = newClient()

func newClient() *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.TLSHandshakeTimeout = tlsHandshakeTimeout
	transport.DialContext = (&net.Dialer{
		Timeout:   dialContextTimeout,
		KeepAlive: dialContextKeepAlive,
	}).DialContext
	return &http.Client{
		Transport: WithCompression(
			WithRetry(defaultMaxAttempts,
				transport,
			),
		),
	}
}
