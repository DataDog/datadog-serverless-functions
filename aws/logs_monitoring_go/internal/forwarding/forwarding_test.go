// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import (
	"compress/gzip"
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
)

func TestForward(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		statusCode int
		payloads   [][]byte
		cancelCtx  bool
		wantErr    bool
		wantErrMsg string
		wantCalls  int
	}{
		"single_message_accepted": {
			statusCode: http.StatusAccepted,
			payloads:   [][]byte{[]byte("test payload")},
			wantCalls:  1,
		},
		"multiple_messages_accepted": {
			statusCode: http.StatusAccepted,
			payloads:   [][]byte{[]byte("first"), []byte("second"), []byte("third")},
			wantCalls:  3,
		},
		"empty_channel": {
			statusCode: http.StatusAccepted,
			payloads:   [][]byte{},
			wantCalls:  0,
		},
		"server_returns_400": {
			statusCode: http.StatusBadRequest,
			payloads:   [][]byte{[]byte("test payload")},
			wantErr:    true,
			wantErrMsg: "unexpected status from intake",
			wantCalls:  1,
		},
		"server_returns_500": {
			statusCode: http.StatusInternalServerError,
			payloads:   [][]byte{[]byte("test payload")},
			wantErr:    true,
			wantErrMsg: "unexpected status from intake",
			wantCalls:  1,
		},
		"context_cancelled": {
			statusCode: http.StatusAccepted,
			payloads:   [][]byte{[]byte("test payload")},
			cancelCtx:  true,
			wantErr:    true,
			wantCalls:  0,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var callCount atomic.Int32

			server := httptest.NewServer(http.HandlerFunc(func(rw http.ResponseWriter, req *http.Request) {
				callCount.Add(1)

				if got := req.Header.Get("DD-API-KEY"); got != "test-api-key" {
					t.Errorf("DD-API-KEY = %q, want %q", got, "test-api-key")
				}
				if got := req.Header.Get("Content-Encoding"); got != "gzip" {
					t.Errorf("Content-Encoding = %q, want %q", got, "gzip")
				}

				gr, err := gzip.NewReader(req.Body)
				if err != nil {
					t.Errorf("body is not valid gzip: %v", err)
					return
				}
				defer func() {
					if err := gr.Close(); err != nil {
						t.Errorf("failed to close gzip reader: %v", err)
					}
				}()

				if _, err := io.ReadAll(gr); err != nil {
					t.Errorf("failed to read gzip body: %v", err)
				}

				rw.WriteHeader(tc.statusCode)
			}))
			defer server.Close()

			f := Forwarder{
				Config: config.Config{
					IntakeURL: server.URL,
					APIKey:    "test-api-key",
				},
				Client: server.Client(),
			}

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			if tc.cancelCtx {
				cancel()
			}

			in := make(chan []byte, len(tc.payloads))
			for _, p := range tc.payloads {
				in <- p
			}
			close(in)

			err := f.Forward(ctx, in)

			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				if tc.wantErrMsg != "" && !strings.Contains(err.Error(), tc.wantErrMsg) {
					t.Errorf("error %q should contain %q", err.Error(), tc.wantErrMsg)
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got := int(callCount.Load()); got != tc.wantCalls {
				t.Errorf("server called %d times, want %d", got, tc.wantCalls)
			}
		})
	}
}
