// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"iter"
	"log/slog"
	"sync/atomic"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-lambda-go/lambdacontext"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/aws-sdk-go-v2/service/s3/types"
)

const prefix = "failed_events/"

type S3 struct {
	client   sdkclient.S3
	bucket   string
	sequence atomic.Int64
}

func newS3(client sdkclient.S3, bucket string) *S3 {
	return &S3{client: client, bucket: bucket}
}

func (s *S3) Store(ctx context.Context, batch Batch) error {
	invocationID := "unknown"
	if lc, ok := lambdacontext.FromContext(ctx); ok {
		invocationID = lc.AwsRequestID
	}

	datetime := time.Now().UTC().Format("2006/01/02/150405000")
	key := fmt.Sprintf("%s%s_%s_%d.json", prefix, datetime, invocationID, s.sequence.Add(1))

	slog.DebugContext(ctx, "storing batch to S3",
		slog.String("bucket", s.bucket),
		slog.String("key", key),
		slog.Int("batch_bytes", len(batch.Data)),
	)

	_, err := s.client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:   aws.String(s.bucket),
		Key:      aws.String(key),
		Body:     bytes.NewReader(batch.Data),
		Metadata: map[string]string{metadataStorageTagKey: batch.StorageTag},
	})
	if err != nil {
		return err
	}

	return nil
}

func (s *S3) Fetch(ctx context.Context) iter.Seq2[Batch, error] {
	return func(yield func(Batch, error) bool) {
		listOut, err := s.client.ListObjectsV2(ctx,
			&s3.ListObjectsV2Input{
				Bucket: aws.String(s.bucket),
				Prefix: aws.String(prefix),
			},
		)
		if err != nil {
			yield(Batch{}, fmt.Errorf("list objects: %w", err))
			return
		}

		slog.DebugContext(ctx, "fetched retry batches from S3", slog.Int("objects", len(listOut.Contents)))

		for _, object := range listOut.Contents {
			storedBatch, err := s.getBatch(ctx, object)
			if err != nil {
				yield(storedBatch, err)
				return
			}

			if !yield(storedBatch, err) {
				return
			}
		}
	}
}

func (s *S3) getBatch(ctx context.Context, object types.Object) (Batch, error) {
	out, err := s.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(aws.ToString(object.Key)),
	})
	if err != nil {
		return Batch{}, fmt.Errorf("get object: %w", err)
	}
	defer func() {
		if err := out.Body.Close(); err != nil {
			slog.WarnContext(ctx, "close body", slog.Any("error", err))
		}
	}()

	batch, err := io.ReadAll(out.Body)
	if err != nil {
		return Batch{}, fmt.Errorf("read body: %w", err)
	}

	return Batch{
		Data:       batch,
		StorageTag: out.Metadata[metadataStorageTagKey],
		DeleteKey:  aws.ToString(object.Key),
	}, nil
}

func (s *S3) Delete(ctx context.Context, batch Batch) error {
	_, err := s.client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(batch.DeleteKey),
	})
	if err != nil {
		return err
	}

	return nil
}
