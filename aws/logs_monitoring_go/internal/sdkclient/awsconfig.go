// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

import (
	"context"
	"crypto/fips140"
	"fmt"
	"log/slog"
	"sync"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
)

var AWSConfig = sync.OnceValues(func() (aws.Config, error) {
	cfg, err := awsconfig.LoadDefaultConfig(context.TODO(), fipsLoadOption())
	if err != nil {
		return aws.Config{}, fmt.Errorf("load aws config: %w", err)
	}
	return cfg, nil
})

func fipsLoadOption() awsconfig.LoadOptionsFunc {
	if !fips140.Enabled() {
		return awsconfig.WithUseFIPSEndpoint(aws.FIPSEndpointStateUnset)
	}

	slog.Info("FIPS 140-3 mode active, enabling AWS SDK FIPS endpoints")
	return awsconfig.WithUseFIPSEndpoint(aws.FIPSEndpointStateEnabled)
}
