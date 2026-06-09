// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=s3.go -package=$GOPACKAGE -destination=s3_mockgen.go

import (
	"context"
	"sync"

	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// See https://github.com/aws/aws-sdk-go-v2/issues/3416 for future configuration

var GetS3 = sync.OnceValues(func() (S3, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return s3.NewFromConfig(cfg), nil
})

type S3 interface {
	PutObject(ctx context.Context, params *s3.PutObjectInput, optFns ...func(*s3.Options)) (*s3.PutObjectOutput, error)
	ListObjectsV2(ctx context.Context, params *s3.ListObjectsV2Input, optFns ...func(*s3.Options)) (*s3.ListObjectsV2Output, error)
	GetObject(ctx context.Context, params *s3.GetObjectInput, optFns ...func(*s3.Options)) (*s3.GetObjectOutput, error)
	DeleteObject(ctx context.Context, params *s3.DeleteObjectInput, optFns ...func(*s3.Options)) (*s3.DeleteObjectOutput, error)
}
