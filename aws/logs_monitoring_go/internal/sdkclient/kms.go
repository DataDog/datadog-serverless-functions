// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=kms.go -package=mocks -destination=mocks/kms.go

import (
	"context"
	"sync"

	"github.com/aws/aws-sdk-go-v2/service/kms"
)

var GetKMS = sync.OnceValues(func() (KMS, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return kms.NewFromConfig(cfg), nil
})

type KMS interface {
	Decrypt(ctx context.Context, params *kms.DecryptInput, optFns ...func(*kms.Options)) (*kms.DecryptOutput, error)
}
