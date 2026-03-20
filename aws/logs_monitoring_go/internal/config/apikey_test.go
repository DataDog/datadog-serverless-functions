package config

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestResolveAPIKey(t *testing.T) {
	t.Run("no env vars set", func(t *testing.T) {
		cfg := &Config{}
		err := cfg.resolveAPIKey(context.Background())
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "no API key configured")
	})

	t.Run("DD_API_KEY set", func(t *testing.T) {
		t.Setenv("DD_API_KEY", "abcdef1234567890abcdef1234567890")

		cfg := &Config{}
		err := cfg.resolveAPIKey(context.Background())
		assert.NoError(t, err)
		assert.Equal(t, "abcdef1234567890abcdef1234567890", cfg.APIKey)
	})

	t.Run("DD_API_KEY_SECRET_ARN takes priority over DD_API_KEY", func(t *testing.T) {
		t.Setenv("DD_API_KEY", "abcdef1234567890abcdef1234567890")
		t.Setenv("DD_API_KEY_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-secret")

		cfg := &Config{}
		err := cfg.resolveAPIKey(context.Background())
		assert.NoError(t, err)
		assert.Equal(t, "", cfg.APIKey, "should resolve from Secrets Manager, not DD_API_KEY")
	})
}

func TestValidateAPIKey(t *testing.T) {
	t.Parallel()

	t.Run("empty API key", func(t *testing.T) {
		t.Parallel()

		cfg := &Config{APIKey: ""}
		err := cfg.validateAPIKey()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "missing Datadog API key")
	})

	t.Run("wrong length", func(t *testing.T) {
		t.Parallel()

		cfg := &Config{APIKey: "tooshort", Site: "datadoghq.com"}
		err := cfg.validateAPIKey()
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "expected 32 characters, got 8")
	})

	t.Run("valid key with successful validation", func(t *testing.T) {
		t.Parallel()

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			assert.Equal(t, "/api/v1/validate", r.URL.Path)
			assert.Equal(t, "abcdef1234567890abcdef1234567890", r.URL.Query().Get("api_key"))
			w.WriteHeader(http.StatusOK)
		}))
		defer server.Close()

		cfg := &Config{
			APIKey: "abcdef1234567890abcdef1234567890",
			APIURL: server.URL,
			Site:   "datadoghq.com",
		}
		err := cfg.validateAPIKey()
		assert.NoError(t, err)
	})

	t.Run("valid key with 403 response", func(t *testing.T) {
		t.Parallel()

		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.WriteHeader(http.StatusForbidden)
		}))
		defer server.Close()

		cfg := &Config{
			APIKey: "abcdef1234567890abcdef1234567890",
			APIURL: server.URL,
			Site:   "datadoghq.com",
		}
		err := cfg.validateAPIKey()
		assert.NoError(t, err)
	})

	t.Run("retryable 500 then recovers with 200", func(t *testing.T) {
		t.Parallel()

		callCount := 0
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			callCount++
			if callCount <= 1 {
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			w.WriteHeader(http.StatusOK)
		}))
		defer server.Close()

		cfg := &Config{
			APIKey: "abcdef1234567890abcdef1234567890",
			APIURL: server.URL,
			Site:   "datadoghq.com",
		}
		err := cfg.validateAPIKey()
		assert.NoError(t, err)
		assert.Equal(t, 2, callCount, "should have retried once then succeeded")
	})
}
