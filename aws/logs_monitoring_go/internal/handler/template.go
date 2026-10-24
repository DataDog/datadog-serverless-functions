// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handler

import (
	"slices"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
)

type Template struct {
	service string
	source  string
	tags    model.Tags
}

func NewTemplate(service, source string, tags model.Tags) Template {
	return Template{service: service, source: source, tags: slices.Clip(tags)}
}

func (t Template) NewEntry() model.LogEntry {
	entry := model.NewLogEntry()
	entry.Service = t.service
	entry.Source = t.source
	entry.Tags = t.tags
	return entry
}
