// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handler

import "github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"

const (
	sourceCloudTrail  model.Source = "cloudtrail"
	sourceCloudWatch  model.Source = "cloudwatch"
	sourceKinesis     model.Source = "kinesis"
	sourceLambda      model.Source = "lambda"
	sourceS3          model.Source = "s3"
	sourceSecurityHub model.Source = "securityhub"
	sourceSNS         model.Source = "sns"
	sourceWAF         model.Source = "waf"
)

func CustomSource(s string) model.Source {
	return model.Source(s)
}
