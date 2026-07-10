// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package storing

import (
	"context"
	"encoding/json"
	"fmt"
	"iter"
	"log/slog"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batching"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/concurrent"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
	"golang.org/x/sync/errgroup"
)

const (
	maxSizePerSQSMessage = 1000 * 1024 // Overhead for other attributes than message body
	maxNumberOfMessages  = 10
	polling              = 100
	visibilityTimeout    = 6 * 60
	waitTimeSeconds      = 0
)

type SQS struct {
	client sdkclient.SQS
	queue  string
}

func newSQS(client sdkclient.SQS, queue string) *SQS {
	return &SQS{client: client, queue: queue}
}

func (s *SQS) Store(ctx context.Context, batch Batch) error {
	slog.DebugContext(ctx, "storing batch to SQS",
		slog.String("queue", s.queue),
		slog.Int("batch_bytes", len(batch.Data)),
	)

	var logs []json.RawMessage
	if err := json.Unmarshal(batch.Data, &logs); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	eg, ctx := errgroup.WithContext(ctx)

	in := make(chan json.RawMessage, 10)
	eg.Go(func() error {
		defer close(in)
		for _, log := range logs {
			if err := concurrent.SafeSender(ctx, in, log); err != nil {
				return err
			}
		}
		return nil
	})

	out := make(chan json.RawMessage)
	eg.Go(func() error {
		defer close(out)
		batcher := batching.New[json.RawMessage](batching.NewConfig(maxSizePerSQSMessage, maxSizePerSQSMessage, 0))
		return batcher.Start(ctx, in, out)
	})

	eg.Go(func() error {
		for {
			messageBody, ok, _ := concurrent.SafeReader(ctx, out)
			if !ok {
				break
			}

			_, err := s.client.SendMessage(ctx, &sqs.SendMessageInput{
				QueueUrl:    &s.queue,
				MessageBody: aws.String(string(messageBody)),
				MessageAttributes: map[string]types.MessageAttributeValue{
					metadataStorageTagKey: {
						DataType:    aws.String("String"),
						StringValue: aws.String(batch.StorageTag),
					},
				},
			})
			if err != nil {
				return fmt.Errorf("send message: %w", err)
			}
		}
		return nil
	})

	return eg.Wait()
}

func (s *SQS) Fetch(ctx context.Context) iter.Seq2[Batch, error] {
	return func(yield func(Batch, error) bool) {
		for range polling {
			out, err := s.client.ReceiveMessage(ctx, &sqs.ReceiveMessageInput{
				QueueUrl:              &s.queue,
				MaxNumberOfMessages:   maxNumberOfMessages,
				MessageAttributeNames: []string{metadataStorageTagKey},
				VisibilityTimeout:     visibilityTimeout,
				WaitTimeSeconds:       waitTimeSeconds,
			})
			if err != nil {
				yield(Batch{}, fmt.Errorf("receive message: %w", err))
				return
			}

			if len(out.Messages) == 0 {
				return
			}

			slog.DebugContext(ctx, "received retry messages from SQS", slog.Int("messages", len(out.Messages)))

			for _, message := range out.Messages {
				storedBatch := Batch{
					Data:       []byte(aws.ToString(message.Body)),
					StorageTag: aws.ToString(message.MessageAttributes[metadataStorageTagKey].StringValue),
					DeleteKey:  aws.ToString(message.ReceiptHandle),
				}
				if !yield(storedBatch, nil) {
					return
				}
			}
		}
	}
}

func (s *SQS) Delete(ctx context.Context, batch Batch) error {
	_, err := s.client.DeleteMessage(ctx, &sqs.DeleteMessageInput{
		QueueUrl:      &s.queue,
		ReceiptHandle: &batch.DeleteKey,
	})
	if err != nil {
		return fmt.Errorf("delete message: %w", err)
	}

	return nil
}
