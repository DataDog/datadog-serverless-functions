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
	"net/http"
	"sync"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/apikey"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/pipeline"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/storing"

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

	lambda.Start(handleRequest(cfg, httpclient.Client))
}

func handleRequest(cfg *config.Config, client *http.Client) func(ctx context.Context, awsevent json.RawMessage) (any, error) {
	return func(ctx context.Context, awsevent json.RawMessage) (any, error) {
		var wg sync.WaitGroup

		var invokeErr error
		if cfg.AdditionalTargets != nil {
			wg.Go(func() {
				invokeErr = sdkclient.InvokeTargets(ctx, cfg.AdditionalTargets, awsevent)
			})
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
		var storageErr error
		if cfg.StoreOnFail {
			storageOpts := storing.Options{S3Bucket: cfg.S3RetryBucketName, SQSQueue: cfg.SQSQueueURL}
			if storage, storageErr = storing.NewStorage(storageOpts); storageErr != nil {
				return nil, fmt.Errorf("new storage: %w", storageErr)
			}
		}

		forwarder := forwarding.NewForwarder(
			forwarderCfg,
			client,
			storage,
		)

		out, pipelineErr := pipeline.New(handlerCfg, scrubber, filterer, forwarder).Start(ctx, awsevent)

		wg.Wait()
		return out, errors.Join(invokeErr, pipelineErr)
	}
}
