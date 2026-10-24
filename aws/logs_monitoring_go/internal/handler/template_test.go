// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handler

import (
	"testing"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/model"
	"github.com/stretchr/testify/require"
)

func TestTemplate_NewEntryDoesNotShareTags(t *testing.T) {
	t.Parallel()

	tags := make(model.Tags, 0, 4)
	tags = append(tags, "env:prod")
	tmpl := NewTemplate("", "", tags)

	first := tmpl.NewEntry()
	first.Tags.Add(model.FunctionNameKey, "one")

	second := tmpl.NewEntry()
	second.Tags.Add(model.FunctionNameKey, "two")

	require.Equal(t, model.Tags{"env:prod", "functionname:one"}, first.Tags)
	require.Equal(t, model.Tags{"env:prod", "functionname:two"}, second.Tags)
}
