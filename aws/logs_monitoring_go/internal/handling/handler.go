// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/filtering"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/scrubbing"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
)

type Handler interface {
	Handle(ctx context.Context, event json.RawMessage, out chan<- model.LogEntry) error
}

type Config struct {
	Scrubber            *scrubbing.Scrubber
	Filterer            *filtering.Filterer
	Host                string
	Service             string
	Source              string
	Tags                model.Tags
	S3MultilineLogRegex *regexp.Regexp
	UseFIPS             bool
}

func NewHandler(ctx context.Context, hcfg Config, ct parsing.ContentType) (Handler, error) {
	switch ct {

	case parsing.ContentTypeCloudwatchLogs:
		return NewCloudwatch(&hcfg), nil

	case parsing.ContentTypeS3:
		client, err := sdkclient.GetS3(ctx, hcfg.UseFIPS)
		if err != nil {
			return nil, err
		}
		return NewS3(&hcfg, client), nil

	case parsing.ContentTypeKinesis:
		return NewKinesis(&hcfg), nil

	case parsing.ContentTypeEventBridge:
		return NewEventBridge(&hcfg), nil

	case parsing.ContentTypeSNS:
		return NewSNS(&hcfg), nil

	default:
		return nil, fmt.Errorf("unsupported content type: %v", ct)
	}
}
