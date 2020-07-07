/*
 * Unless explicitly stated otherwise all files in this repository are licensed
 * under the Apache License Version 2.0.
 *
 * This product includes software developed at Datadog (https://www.datadoghq.com/).
 * Copyright 2020 Datadog, Inc.
 */
package main

import (
	"C"
	"context"
	"fmt"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring/trace_forwarder/internal/apm"
)
import (
	"github.com/DataDog/datadog-agent/pkg/trace/obfuscate"
	"github.com/DataDog/datadog-agent/pkg/trace/pb"
)

var (
	obfuscator     *obfuscate.Obfuscator
	edgeConnection apm.TraceEdgeConnection
)

// Configure will set up the bindings
//export Configure
func Configure(rootURL, apiKey string) {
	// Need to make a copy of these values, otherwise the underlying memory
	// might be cleaned up by the runtime.
	localRootURL := fmt.Sprintf("%s", rootURL)
	localAPIKey := fmt.Sprintf("%s", apiKey)

	obfuscator = obfuscate.NewObfuscator(&obfuscate.Config{
		ES: obfuscate.JSONSettings{
			Enabled: true,
		},
		Mongo: obfuscate.JSONSettings{
			Enabled: true,
		},
		RemoveQueryString: true,
		RemovePathDigits:  true,
		RemoveStackTraces: true,
		Redis:             true,
		Memcached:         true,
	})
	edgeConnection = apm.CreateTraceEdgeConnection(localRootURL, localAPIKey)
}

// ForwardTraces will perform filtering and log forwarding to the trace intake
// returns 0 on success, 1 on error
//export ForwardTraces
func ForwardTraces(content string, tags string) int {
	tracePayloads, err := apm.ProcessTrace(content, obfuscator, tags)
	if err != nil {
		fmt.Printf("Couldn't forward traces: %v", err)
		return 1
	}

	combinedPayload := combinePayloads(tracePayloads)

	err = edgeConnection.SendTraces(context.Background(), combinedPayload, 3)
	if err != nil {
		fmt.Printf("Failed to send traces with error %v\n", err)
		return 1
	}

	stats := apm.ComputeAPMStats(combinedPayload)
	err = edgeConnection.SendStats(context.Background(), stats, 3)
	if err != nil {
		fmt.Printf("Failed to send trace stats with error %v\n", err)
		return 1
	}

	return 0
}

// Combine payloads into one
// Assumes that all payloads have the same HostName and Env
func combinePayloads(tracePayloads []*pb.TracePayload) *pb.TracePayload {
	combinedPayload := &pb.TracePayload{
		HostName: tracePayloads[0].HostName,
		Env:      tracePayloads[0].Env,
		Traces:   make([]*pb.APITrace, 0),
	}
	for _, tracePayload := range tracePayloads {
		combinedPayload.Traces = append(combinedPayload.Traces, tracePayload.Traces...)
	}
	fmt.Sprintf("aggregated %d traces into single payload", len(combinedPayload.Traces))
	return combinedPayload
}

func main() {}
