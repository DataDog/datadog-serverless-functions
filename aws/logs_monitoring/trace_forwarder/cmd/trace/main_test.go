/*
 * Unless explicitly stated otherwise all files in this repository are licensed
 * under the Apache License Version 2.0.
 *
 * This product includes software developed at Datadog (https://www.datadoghq.com/).
 * Copyright 2021 Datadog, Inc.
 */
package main

import (
	"io/ioutil"
	"os"
	"testing"

	"github.com/DataDog/datadog-agent/pkg/trace/pb"
	"github.com/stretchr/testify/assert"
)

func TestUnmarshalSerializedTraces(t *testing.T) {
	input := "[{\"message\":\"traces\",\"tags\":\"tag1:value\"},{\"message\":\"traces\",\"tags\":\"tag1:value\"}]"

	output, _ := unmarshalSerializedTraces(input)

	assert.Equal(t, output[0].Message, "traces")
	assert.Equal(t, output[0].Tags, "tag1:value")
	assert.Equal(t, output[1].Message, "traces")
	assert.Equal(t, output[1].Tags, "tag1:value")
}

func TestAggregateTracePayloadsByEnv(t *testing.T) {
	payload1 := pb.TracePayload{
		HostName: "",
		Env:      "none",
		Traces:   make([]*pb.APITrace, 0),
	}

	payload2 := pb.TracePayload{
		HostName: "",
		Env:      "",
		Traces:   make([]*pb.APITrace, 0),
	}

	payload3 := pb.TracePayload{
		HostName: "",
		Env:      "",
		Traces:   make([]*pb.APITrace, 0),
	}

	input := []*pb.TracePayload{&payload1, &payload2, &payload3}
	output := aggregateTracePayloadsByEnv(input)

	assert.Equal(t, len(output), 2)
}

func TestForwardTracesWithXRayRoot(t *testing.T) {
	inputFile := "testdata/xray-parent.json"
	file, err := os.Open(inputFile)
	assert.NoError(t, err)
	defer file.Close()

	contents, err := ioutil.ReadAll(file)
	input := string(contents)

	assert.NoError(t, err, "Couldn't read contents of test file")

	// We capture stdout
	originalStdout := os.Stdout
	r, w, _ := os.Pipe()
	os.Stdout = w

	result := ForwardTraces(input)

	w.Close()
	out, _ := ioutil.ReadAll(r)
	os.Stdout = originalStdout

	outputLog := string(out)

	assert.Equal(t, result, 0)
	assert.Equal(t, outputLog, "No traces to forward")
}
