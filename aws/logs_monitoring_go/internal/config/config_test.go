package config

import (
	"context"
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestDeriveURLs(t *testing.T) {
	t.Run("defaults", func(t *testing.T) {
		cfg := &Config{Site: "datadoghq.com", NoSSL: false}
		cfg.deriveURLs()
		assert.Equal(t, "https://http-intake.logs.datadoghq.com", cfg.IntakeURL)
		assert.Equal(t, "https://api.datadoghq.com", cfg.APIURL)
	})

	t.Run("NoSSL switches scheme to http", func(t *testing.T) {
		cfg := &Config{Site: "datadoghq.com", NoSSL: true}
		cfg.deriveURLs()
		assert.Equal(t, "http://http-intake.logs.datadoghq.com", cfg.IntakeURL)
		assert.Equal(t, "http://api.datadoghq.com", cfg.APIURL)
	})

	t.Run("custom site", func(t *testing.T) {
		cfg := &Config{Site: "datadoghq.eu", NoSSL: false}
		cfg.deriveURLs()
		assert.Equal(t, "https://http-intake.logs.datadoghq.eu", cfg.IntakeURL)
		assert.Equal(t, "https://api.datadoghq.eu", cfg.APIURL)
	})

	t.Run("DD_URL override", func(t *testing.T) {
		t.Setenv("DD_URL", "custom-intake.example.com")

		cfg := &Config{Site: "datadoghq.com", NoSSL: false}
		cfg.deriveURLs()
		assert.Equal(t, "custom-intake.example.com", cfg.IntakeURL)
	})

	t.Run("DD_API_URL override", func(t *testing.T) {
		t.Setenv("DD_API_URL", "https://custom-api.example.com")

		cfg := &Config{Site: "datadoghq.com", NoSSL: false}
		cfg.deriveURLs()
		assert.Equal(t, "https://custom-api.example.com", cfg.APIURL)
	})
}

func TestLoad(t *testing.T) {
	t.Run("defaults with valid API key", func(t *testing.T) {
		t.Setenv("DD_API_KEY", "abcdef1234567890abcdef1234567890")

		cfg, err := Load(context.Background())
		assert.NoError(t, err)
		assert.Equal(t, "datadoghq.com", cfg.Site)
		assert.Equal(t, 443, cfg.Port)
		assert.Equal(t, false, cfg.NoSSL)
		assert.Equal(t, false, cfg.SkipSSLValidation)
		assert.Equal(t, "INFO", cfg.LogLevel)
		assert.Equal(t, false, cfg.UseFIPS)
		assert.Equal(t, "https://http-intake.logs.datadoghq.com", cfg.IntakeURL)
		assert.Equal(t, "abcdef1234567890abcdef1234567890", cfg.APIKey)
	})

	t.Run("custom env vars", func(t *testing.T) {
		t.Setenv("DD_API_KEY", "abcdef1234567890abcdef1234567890")
		t.Setenv("DD_SITE", "datadoghq.eu")
		t.Setenv("DD_PORT", "8080")
		t.Setenv("DD_NO_SSL", "true")
		t.Setenv("DD_LOG_LEVEL", "DEBUG")

		cfg, err := Load(context.Background())
		assert.NoError(t, err)
		assert.Equal(t, "datadoghq.eu", cfg.Site)
		assert.Equal(t, 8080, cfg.Port)
		assert.Equal(t, true, cfg.NoSSL)
		assert.Equal(t, "DEBUG", cfg.LogLevel)
		assert.Equal(t, "http://api.datadoghq.eu", cfg.APIURL)
	})

	t.Run("missing API key returns error", func(t *testing.T) {
		_, err := Load(context.Background())
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "resolving API key")
	})
}
