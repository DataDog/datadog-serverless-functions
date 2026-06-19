// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/forwarding"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"golang.org/x/sync/errgroup"

	awsevents "github.com/aws/aws-lambda-go/events"
)

type Pipeline struct {
	hcfg      handling.Config
	scrubber  *scrubbing.Scrubber
	filterer  *filtering.Filterer
	forwarder *forwarding.Forwarder
}

func New(
	hcfg handling.Config,
	scrubber *scrubbing.Scrubber,
	filterer *filtering.Filterer,
	forwarder *forwarding.Forwarder,
) Pipeline {
	return Pipeline{
		hcfg:      hcfg,
		scrubber:  scrubber,
		filterer:  filterer,
		forwarder: forwarder,
	}
}

func (p Pipeline) Start(ctx context.Context, awsevent json.RawMessage) (any, error) {
	if parsing.IsSQS(awsevent) {
		events, err := parsing.SQS(awsevent)
		if err != nil {
			return nil, err
		}

		return p.startSQS(ctx, events)
	}

	event, err := parsing.Parse(awsevent)
	if err != nil {
		return nil, fmt.Errorf("parse: %w", err)
	}

	if event.ContentType == parsing.ContentTypeRetry {
		return nil, p.forwarder.Retry(ctx)
	}

	return nil, p.run(ctx, event)
}

func (p Pipeline) startSQS(ctx context.Context, events []parsing.SQSEvent) (sqsEventResponse json.RawMessage, err error) {
	var response awsevents.SQSEventResponse
	for i, event := range events {
		err = p.run(ctx, event.Event)
		if err == nil {
			continue
		}

		for _, remaining := range events[i:] {
			response.BatchItemFailures = append(response.BatchItemFailures, awsevents.SQSBatchItemFailure{ItemIdentifier: remaining.SQSReceiptHandle})
		}

		break
	}

	sqsEventResponse, marshallErr := json.Marshal(response)
	err = errors.Join(err, marshallErr)

	return sqsEventResponse, err
}

func (p Pipeline) run(ctx context.Context, event parsing.Event) error {
	eg, ctx := errgroup.WithContext(ctx)

	entries := make(chan model.LogEntry)
	eg.Go(func() error {
		defer close(entries)
		handler, err := handling.NewHandler(p.hcfg, p.scrubber, p.filterer, event.ContentType)
		if err != nil {
			return fmt.Errorf("new handler: %w", err)
		}

		if err := handler.Handle(ctx, event.Payload, entries); err != nil {
			return fmt.Errorf("handle: %w", err)
		}
		return nil
	})

	err := p.forwarder.Start(ctx, entries, forwarding.StorageTag(event.ContentType))
	if waitErr := eg.Wait(); waitErr != nil {
		return errors.Join(err, waitErr)
	}

	return err
}
