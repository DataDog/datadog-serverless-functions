// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"fmt"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/aws/arn"
	"github.com/aws/aws-sdk-go-v2/service/ssm"
)

type SSMAPIKeySource struct {
	Client sdkclient.SSM
	Name   string
}

func (ks *SSMAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	out, err := ks.Client.GetParameter(ctx, &ssm.GetParameterInput{
		Name:           aws.String(ks.Name),
		WithDecryption: aws.Bool(true),
	}, func(o *ssm.Options) {
		if parsed, err := arn.Parse(ks.Name); err == nil && parsed.Region != "" {
			o.Region = parsed.Region
		}
	})
	if err != nil {
		return "", fmt.Errorf("get parameter %q: %w", ks.Name, err)
	}

	if out.Parameter == nil {
		return "", fmt.Errorf("no value for parameter %q", ks.Name)
	}

	if out.Parameter.Value == nil {
		return "", fmt.Errorf("no string value for parameter %q", ks.Name)
	}

	return APIKey(strings.TrimSpace(*out.Parameter.Value)), nil
}
