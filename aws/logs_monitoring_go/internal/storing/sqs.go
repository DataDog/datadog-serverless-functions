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
	"math"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/batching"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/sqs"
	"github.com/aws/aws-sdk-go-v2/service/sqs/types"
)

const (
	maxSizePerSQSMessage = 1000 * 1024 // Overhead for other attributes than message body
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
		batching.WithMaxBatchSize(maxSizePerSQSMessage),
		batching.WithMaxItemsPerBatch(math.MaxInt),
	)
	for message, err := range batcher.StartYield(logs) {
		if err != nil {
			return fmt.Errorf("batching: %w", err)
		}

		_, err := s.client.SendMessage(ctx, &sqs.SendMessageInput{
			QueueUrl:    &s.queue,
			MessageBody: aws.String(string(message)),
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
