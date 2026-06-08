// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

import (
	"context"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

const metadataStorageTagKey = "dd-storage-tag"

type Storage interface {
	Put(ctx context.Context, batch []byte, storageTag string) error
	List(ctx context.Context) ([]string, error)
	Get(ctx context.Context, key string) ([]byte, string, error)
	Delete(ctx context.Context, key string) error
}

type Options struct {
	S3Bucket string
}

func NewStorage(ctx context.Context, opts Options) (Storage, error) {
	if opts.S3Bucket != "" {
		s3Client, err := sdkclient.GetS3(ctx)
		if err != nil {
			return nil, err
		}
		return newS3(s3Client, opts.S3Bucket), nil
	}

	return nil, nil
}
