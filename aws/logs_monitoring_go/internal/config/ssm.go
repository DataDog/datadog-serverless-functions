// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

func (c *Config) resolveAPIKeyFromSSM(ctx context.Context, name string) (string, error) {
	ssmClient, err := sdkclient.NewSSM(ctx)
	if err != nil {
		return "", err
	}
	return sdkclient.FetchSSMParameter(ctx, ssmClient, name)
}
