// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=sqs.go -package=$GOPACKAGE -destination=sqs_mockgen.go

import (
	"context"
	"sync"

	"github.com/aws/aws-sdk-go-v2/service/sqs"
)

var GetSQS = sync.OnceValues(func() (SQS, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return sqs.NewFromConfig(cfg), nil
})

type SQS interface {
	SendMessageBatch(ctx context.Context, params *sqs.SendMessageBatchInput, optFns ...func(*sqs.Options)) (*sqs.SendMessageBatchOutput, error)
	ReceiveMessage(ctx context.Context, params *sqs.ReceiveMessageInput, optFns ...func(*sqs.Options)) (*sqs.ReceiveMessageOutput, error)
	DeleteMessage(ctx context.Context, params *sqs.DeleteMessageInput, optFns ...func(*sqs.Options)) (*sqs.DeleteMessageOutput, error)
}
