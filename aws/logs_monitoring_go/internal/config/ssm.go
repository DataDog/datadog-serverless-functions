// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package config

import (
	"context"

	"github.com/aws/aws-sdk-go-v2/aws"
)

func (c *Config) resolveFromSSM(ctx context.Context, awsCfg aws.Config, name string) error {
	return nil
}
