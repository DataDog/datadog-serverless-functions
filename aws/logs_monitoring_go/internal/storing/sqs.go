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
	"math"
	"strconv"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batching"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
)

const (
	maxSizePerSQSMessage = 1 * 1024 * 1024
	maxSizePerSQSBatch   = 1 * 1024 * 1024
	maxMessagePerBatch   = 10
	maxNumberOfMessages  = 10
	polling              = 10
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
	var logs []json.RawMessage
	if err := json.Unmarshal(batch.Data, &logs); err != nil {
		return fmt.Errorf("unmarshal: %w", err)
	}

	batcher := batching.New(
		batching.WithMaxItemSize(maxSizePerSQSMessage),
		batching.WithMaxBatchSize(maxSizePerSQSBatch),
		batching.WithMaxItemsPerBatch(math.MaxInt),
	)
	messages, err := batcher.StartSlice(logs)
	if err != nil {
		return fmt.Errorf("batching: %w", err)
	}

	messageEntries := make([]types.SendMessageBatchRequestEntry, 0, maxMessagePerBatch)
	for i, message := range messages {
		entry := types.SendMessageBatchRequestEntry{
			Id:          aws.String(strconv.Itoa(i)),
			MessageBody: aws.String(string(message)),
			MessageAttributes: map[string]types.MessageAttributeValue{
				metadataStorageTagKey: {
					DataType:    aws.String("String"),
					StringValue: aws.String(batch.StorageTag),
				},
			},
		}

		if len(messageEntries) >= maxMessagePerBatch {
			if err := s.send(ctx, messageEntries); err != nil {
				return err
			}
			messageEntries = messageEntries[:0]
		}
		messageEntries = append(messageEntries, entry)
	}

	return s.send(ctx, messageEntries)
}

func (s *SQS) send(ctx context.Context, entries []types.SendMessageBatchRequestEntry) error {
	if len(entries) == 0 {
		return nil
	}

	out, err := s.client.SendMessageBatch(ctx, &sqs.SendMessageBatchInput{
		Entries:  entries,
		QueueUrl: &s.queue,
	})
	if err != nil {
		return fmt.Errorf("send message batch: %w", err)
	}

	if len(out.Failed) > 0 {
		for _, e := range out.Failed {
			slog.DebugContext(ctx, "failed to send SQS message",
				slog.String("code", aws.ToString(e.Code)),
				slog.String("message", aws.ToString(e.Message)),
				slog.Bool("sender_fault", e.SenderFault),
			)
		}
		return fmt.Errorf("failed to send %d/%d messages", len(out.Failed), len(out.Failed)+len(out.Successful))
	}

	return nil
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

func (s *SQS) Delete(ctx context.Context, failedBatch Batch) error {
	_, err := s.client.DeleteMessage(ctx, &sqs.DeleteMessageInput{
		QueueUrl:      &s.queue,
		ReceiptHandle: &failedBatch.DeleteKey,
	})
	if err != nil {
		return fmt.Errorf("delete message: %w", err)
	}

	return nil
}
