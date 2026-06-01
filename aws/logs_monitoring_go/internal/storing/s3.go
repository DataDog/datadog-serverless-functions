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
	"log/slog"
	"sync/atomic"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-lambda-go/lambdacontext"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

const (
	prefix = "failed_events/"
)

var seq atomic.Int64

type S3 struct {
	client sdkclient.S3
	bucket string
}

func NewS3(client sdkclient.S3, bucket string) *S3 {
	return &S3{client: client, bucket: bucket}
}

func (s *S3) Put(ctx context.Context, batch []byte, storageTag string) error {
	invocationID := "unknown"
	if lc, ok := lambdacontext.FromContext(ctx); ok {
		invocationID = lc.AwsRequestID
	}

	datetime := time.Now().UTC().Format("2006/01/02/150405000")
	key := fmt.Sprintf("%s%s_%s_%d.json", prefix, datetime, invocationID, seq.Add(1))

	_, err := s.client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:   aws.String(s.bucket),
		Key:      aws.String(key),
		Body:     bytes.NewReader(batch),
		Metadata: map[string]string{metadataStorageTagKey: storageTag},
	})
	if err != nil {
		return err
	}

	return nil
}

func (s *S3) List(ctx context.Context) ([]string, error) {
	out, err := s.client.ListObjectsV2(ctx,
		&s3.ListObjectsV2Input{
			Bucket: aws.String(s.bucket),
			Prefix: aws.String(prefix),
		},
	)
	if err != nil {
		return nil, err
	}

	var keys []string
	for _, obj := range out.Contents {
		keys = append(keys, aws.ToString(obj.Key))
	}

	return keys, nil
}

func (s *S3) Get(ctx context.Context, key string) ([]byte, string, error) {
	out, err := s.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, "", err
	}
	defer func() {
		if err := out.Body.Close(); err != nil {
			slog.WarnContext(ctx, "closing body", slog.Any("error", err))
		}
	}()

	batch, err := io.ReadAll(out.Body)
	if err != nil {
		return nil, "", err
	}

	return batch, out.Metadata[metadataStorageTagKey], nil
}

func (s *S3) Delete(ctx context.Context, key string) error {
	_, err := s.client.DeleteObject(ctx, &s3.DeleteObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return err
	}

	return nil
}
