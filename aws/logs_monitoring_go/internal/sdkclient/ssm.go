// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=ssm.go -package=mocks -destination=mocks/ssm.go

import (
	"context"
	"sync"

	"github.com/aws/aws-sdk-go-v2/service/ssm"
)

var GetSSM = sync.OnceValues(func() (SSM, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return ssm.NewFromConfig(cfg), nil
})

type SSM interface {
	GetParameter(ctx context.Context, params *ssm.GetParameterInput, optFns ...func(*ssm.Options)) (*ssm.GetParameterOutput, error)
}
