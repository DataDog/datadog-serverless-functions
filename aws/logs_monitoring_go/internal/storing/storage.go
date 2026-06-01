// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

import (
	"context"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

const metadataStorageTagKey = "dd-storage-tag"

type Storage interface {
	Put(ctx context.Context, batch []byte, storageTag string) error
	List(ctx context.Context) ([]string, error)
	Get(ctx context.Context, key string) ([]byte, string, error)
	Delete(ctx context.Context, key string) error
}

func NewStorage(ctx context.Context, cfg *config.Config) Storage {
	if !cfg.StoreOnFail {
		return nil
	}

	if cfg.S3RetryBucketName != "" {
		s3Client, err := sdkclient.GetS3(ctx, cfg.UseFIPS)
		if err != nil {
			slog.ErrorContext(ctx, "failed to create S3 client for retry storage", slog.Any("error", err))
			return nil
		}

		return NewS3(s3Client, cfg.S3RetryBucketName)
	}

	return nil
}
