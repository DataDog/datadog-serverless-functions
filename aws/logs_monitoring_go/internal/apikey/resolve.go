// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

type Source struct {
	SecretARN string
	SSMName   string
	KMSKey    string
}

type resolver struct {
	name    string
	value   string
	resolve func(ctx context.Context, value string) (string, error)
}

func Resolve(ctx context.Context, src Source) (string, error) {
	return resolve(ctx, []resolver{
		{"secrets manager", src.SecretARN, sdkclient.ResolveFromSecretsManager},
		{"ssm", src.SSMName, sdkclient.ResolveFromSSM},
		{"kms", src.KMSKey, sdkclient.ResolveFromKMS},
	})
}

func resolve(ctx context.Context, resolvers []resolver) (string, error) {
	for _, r := range resolvers {
		value := strings.TrimSpace(r.value)
		if value == "" {
			continue
		}

		slog.DebugContext(ctx, "trying API key resolver", slog.String("source", r.name))

		key, err := r.resolve(ctx, value)
		if err != nil {
			return "", fmt.Errorf("resolve %s: %w", r.name, err)
		}

		slog.DebugContext(ctx, "API key resolved")
		return key, nil
	}

	return "", errors.New("no Datadog API key configured")
}
