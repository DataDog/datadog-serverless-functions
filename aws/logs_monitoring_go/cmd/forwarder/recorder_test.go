// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"bytes"
	"compress/gzip"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/require"
)

type recordedRequest struct {
	Headers map[string]string `json:"headers"`
	Body    json.RawMessage   `json:"body"`
}

type recorder struct {
	*httptest.Server
	request recordedRequest
}

func newRecorder(t *testing.T) *recorder {
	t.Helper()

	rec := &recorder{}
	rec.Server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		require.NoError(t, err)

		if r.Header.Get("Content-Encoding") == "gzip" {
			gr, err := gzip.NewReader(bytes.NewReader(body))
			require.NoError(t, err)

			body, err = io.ReadAll(gr)
			require.NoError(t, err)

			require.NoError(t, gr.Close())
		}

		headers := make(map[string]string)
		for key, vals := range r.Header {
			switch key {
			case "Content-Length", "Accept-Encoding": // non-deterministic
				continue
			}
			headers[key] = vals[0]
		}

		rec.request = recordedRequest{Headers: headers, Body: body}
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(rec.Close)

	return rec
}
