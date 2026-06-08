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

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/pipeline"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
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

	// Will refactor this in the future to not stop the forwarder if the api key resolution or validation fails.
	// We may want to store the events in the storage retry mechanism even in case of API key resolution/expiration
	// so we let the customer some time to configure it properly and not lose any of the events from then.
	err = cfg.ResolveAPIKey(context.Background())
	if err != nil {
		log.Fatal(err)
	}
	err = cfg.ValidateAPIKey(context.Background())
	if err != nil {
		log.Fatal(err)
	}

	lambda.Start(handleRequest(cfg))
}

func handleRequest(cfg *config.Config) func(ctx context.Context, event json.RawMessage) error {
	return func(ctx context.Context, event json.RawMessage) error {
		parsed, err := parsing.Parse(event)
		if err != nil {
			return fmt.Errorf("parse: %w", err)
		}

		if len(parsed) == 0 {
			return errors.New("no events to process")
		}

		filterer := filtering.NewFilterer(cfg.FilterInclude, cfg.FilterExclude)
		scrubber := scrubbing.NewScrubber(cfg.ScrubbingRegex, cfg.ScrubbingReplacement, cfg.ScrubIP, cfg.ScrubEmail)
		handlerCfg := handling.Config{
			Host:                cfg.Host,
			Service:             cfg.Service,
			Source:              cfg.Source,
			Tags:                cfg.Tags,
			S3MultilineLogRegex: cfg.S3MultilineLogRegex,
			UseFIPS:             cfg.UseFIPS,
		}

		forwarderCfg := forwarding.Config{
			APIKey:           cfg.APIKey,
			IntakeURL:        cfg.IntakeURL,
			CompressionLevel: cfg.CompressionLevel,
		}

		var storage storing.Storage
		if cfg.StoreOnFail {
			storageOpts := storing.Options{FIPS: cfg.UseFIPS, S3Bucket: cfg.S3RetryBucketName}
			if storage, err = storing.NewStorage(ctx, storageOpts); err != nil {
				return fmt.Errorf("new storage: %w", err)
			}
		}

		forwarder := forwarding.NewForwarder(
			forwarderCfg,
			httpclient.Client,
			storage,
		)

		return pipeline.New(handlerCfg, scrubber, filterer, forwarder).Start(ctx, parsed)
	}
}
