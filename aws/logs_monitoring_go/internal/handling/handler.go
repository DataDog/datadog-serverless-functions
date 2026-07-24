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
	Service             string
	Source              string
	Tags                model.Tags
	S3MultilineLogRegex *regexp.Regexp
}

func NewHandler(hcfg Config, scrubber *scrubbing.Scrubber, filterer *filtering.Filterer, ct parsing.ContentType) (Handler, error) {
	switch ct {

	case parsing.ContentTypeCloudwatchLogs:
		return newCloudwatch(&hcfg, scrubber, filterer), nil

	case parsing.ContentTypeS3:
		client, err := sdkclient.GetS3()
		if err != nil {
			return nil, err
		}
		return newS3(&hcfg, client, scrubber, filterer), nil

	case parsing.ContentTypeKinesis:
		return newKinesis(&hcfg, scrubber, filterer), nil

	case parsing.ContentTypeEventBridge:
		return newEventBridge(&hcfg, scrubber, filterer), nil

	case parsing.ContentTypeSNS:
		return newSNS(&hcfg, scrubber, filterer), nil

	default:
		return nil, fmt.Errorf("unsupported content type: %v", ct)
	}
}
