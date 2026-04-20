// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

//go:generate go tool mockgen -source=s3_client.go -package=parsing -destination=s3_client_mockgen.go

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awshttp "github.com/aws/aws-sdk-go-v2/aws/transport/http"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

const timeout = 10 * time.Second

type S3APIClient interface {
	GetObject(ctx context.Context, params *s3.GetObjectInput, optFns ...func(*s3.Options)) (*s3.GetObjectOutput, error)
}

func createS3APIClient(ctx context.Context, useFIPS bool) (S3APIClient, error) {
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

func getS3Object(ctx context.Context, client S3APIClient, bucket, key string) (io.ReadCloser, error) {
	result, err := client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(bucket),
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("get object s3://%s/%s: %w", bucket, key, err)
	}

	return result.Body, nil
}
