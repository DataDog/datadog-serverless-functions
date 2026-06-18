// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/apikey"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/pipeline"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storing"

	awsevents "github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatal(err)
	}

	var tlsOpts []httpclient.TLSOption
	if cfg.SkipServerCertificate {
		tlsOpts = append(tlsOpts, httpclient.WithCertificateSkip())
	}
	httpclient.Init(tlsOpts...)

	if err = apikey.Validate(context.Background(), httpclient.Client, cfg.APIURL, cfg.APIKey); err != nil {
		if !cfg.StoreOnFail {
			log.Fatal(fmt.Errorf("no failed event storage set, validate API key: %w", err))
		}
		slog.Error("API key validation", slog.Any("error", err))
	}

	lambda.Start(handleRequest(cfg))
}

func handleRequest(cfg *config.Config) func(ctx context.Context, awsevent json.RawMessage) (any, error) {
	return func(ctx context.Context, awsevent json.RawMessage) (any, error) {
		events, err := parsing.Parse(awsevent)
		if err != nil {
			return nil, fmt.Errorf("parse: %w", err)
		}

		if len(events) == 0 {
			return nil, errors.New("no events to process")
		}

		filterer := filtering.NewFilterer(cfg.FilterInclude, cfg.FilterExclude)
		scrubber := scrubbing.NewScrubber(cfg.ScrubbingRegex, cfg.ScrubbingReplacement, cfg.ScrubIP, cfg.ScrubEmail)
		handlerCfg := handling.Config{
			Host:                cfg.Host,
			Service:             cfg.Service,
			Source:              cfg.Source,
			Tags:                cfg.Tags,
			S3MultilineLogRegex: cfg.S3MultilineLogRegex,
		}

		forwarderCfg := forwarding.Config{
			APIKey:           cfg.APIKey,
			IntakeURL:        cfg.IntakeURL,
			CompressionLevel: cfg.CompressionLevel,
		}

		var storage storing.Storage
		if cfg.StoreOnFail {
			storageOpts := storing.Options{S3Bucket: cfg.S3RetryBucketName}
			if storage, err = storing.NewStorage(ctx, storageOpts); err != nil {
				return nil, fmt.Errorf("new storage: %w", err)
			}
		}

		forwarder := forwarding.NewForwarder(
			forwarderCfg,
			httpclient.Client,
			storage,
		)

		for i, event := range events {
			if event.ContentType == parsing.ContentTypeRetry {
				if err := forwarder.Retry(ctx); err != nil {
					return nil, fmt.Errorf("retry: %w", err)
				}
				return nil, nil
			}

			handler, err := handling.NewHandler(handlerCfg, scrubber, filterer, event.ContentType)
			if err != nil {
				return nil, fmt.Errorf("new handler: %w", err)
			}

			err = pipeline.New(handler, forwarder).Start(ctx, event)
			if err == nil {
				continue
			}

			if event.SQSReceiptHandle != "" {
				return nil, err
			}

			var response awsevents.SQSEventResponse
			for _, remaining := range events[i:] {
				response.BatchItemFailures = append(response.BatchItemFailures, awsevents.SQSBatchItemFailure{ItemIdentifier: remaining.SQSReceiptHandle})
			}

			sqsBatchResponse, marshallErr := json.Marshal(response)
			if marshallErr != nil {
				return nil, errors.Join(err, marshallErr)
			}
			return sqsBatchResponse, err
		}

		return nil, nil
	}
}
