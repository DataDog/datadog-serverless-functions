// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package pipeline

import (
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/config"
	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/handling"
)

type Run struct {
	Cfg     *config.Config
	Handler handling.Handler
	Storage string
}

func NewRun(cfg *config.Config, handler handling.Handler, storage string) *Run {
	return &Run{
		Cfg:     cfg,
		Handler: handler,
		Storage: storage,
	}
}
