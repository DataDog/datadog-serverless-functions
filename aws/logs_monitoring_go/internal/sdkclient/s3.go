// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=s3.go -package=$GOPACKAGE -destination=s3_mockgen.go

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// See https://github.com/aws/aws-sdk-go-v2/issues/3416 for future configuration
const timeout = 10 * time.Second

var (
	s3ClientOnce sync.Once
	s3Client     S3
	s3ClientErr  error
)

type S3 interface {
	PutObject(ctx context.Context, params *s3.PutObjectInput, optFns ...func(*s3.Options)) (*s3.PutObjectOutput, error)
	ListObjectsV2(ctx context.Context, params *s3.ListObjectsV2Input, optFns ...func(*s3.Options)) (*s3.ListObjectsV2Output, error)
	GetObject(ctx context.Context, params *s3.GetObjectInput, optFns ...func(*s3.Options)) (*s3.GetObjectOutput, error)
	DeleteObject(ctx context.Context, params *s3.DeleteObjectInput, optFns ...func(*s3.Options)) (*s3.DeleteObjectOutput, error)
}

func GetS3(ctx context.Context, useFIPS bool) (S3, error) {
	s3ClientOnce.Do(func() {
		s3Client, s3ClientErr = newS3(ctx, useFIPS)
	})
	return s3Client, s3ClientErr
}

func newS3(ctx context.Context, useFIPS bool) (S3, error) {
	cfg, err := awsconfig.LoadDefaultConfig(ctx, awsconfig.WithHTTPClient(awshttp.NewBuildableClient().WithTimeout(timeout)))
	if err != nil {
		return nil, err
	}

	resolver := s3.NewDefaultEndpointResolverV2()
	params := s3.EndpointParameters{
		Region:  aws.String(cfg.Region),
		UseFIPS: aws.Bool(useFIPS),
	}

	endpoint, err := resolver.ResolveEndpoint(ctx, params)
	if err != nil && useFIPS {
		slog.Warn("FIPS endpoint not available, falling back to standard endpoint", slog.String("service", "s3"), slog.String("region", cfg.Region))
		params.UseFIPS = aws.Bool(false)
		endpoint, err = resolver.ResolveEndpoint(ctx, params)
	}
	if err != nil {
		return nil, fmt.Errorf("resolve endpoint: %w", err)
	}

	return s3.NewFromConfig(cfg, func(o *s3.Options) {
		o.BaseEndpoint = aws.String(endpoint.URI.String())
	}), nil
}
