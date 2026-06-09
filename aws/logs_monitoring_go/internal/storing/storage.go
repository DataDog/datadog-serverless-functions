// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

import (
	"context"
	"encoding/json"
	"iter"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

const metadataStorageTagKey = "dd-storage-tag"

type Batch struct {
	Data         json.RawMessage
	StorageTag   string
	DeleteHandle string
}

type Storage interface {
	Store(ctx context.Context, batch Batch) error
	Fetch(ctx context.Context) iter.Seq2[Batch, error]
	Delete(ctx context.Context, batch Batch) error
}

type Options struct {
	S3Bucket string
	SQSQueue string
}

func NewStorage(opts Options) (Storage, error) {
	if opts.SQSQueue != "" {
		sqsClient, err := sdkclient.GetSQS()
		if err != nil {
			return nil, err
		}
		return newSQS(sqsClient, opts.SQSQueue), nil
	}

	if opts.S3Bucket != "" {
		s3Client, err := sdkclient.GetS3()
		if err != nil {
			return nil, err
		}
		return newS3(s3Client, opts.S3Bucket), nil
	}

	return nil, nil
}
