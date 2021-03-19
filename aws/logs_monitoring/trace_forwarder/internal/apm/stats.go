/*
 * Unless explicitly stated otherwise all files in this repository are licensed
 * under the Apache License Version 2.0.
 *
 * This product includes software developed at Datadog (https://www.datadoghq.com/).
 * Copyright 2021 Datadog, Inc.
 */
package apm

import (
	"github.com/DataDog/datadog-agent/pkg/trace/pb"
	"github.com/DataDog/datadog-agent/pkg/trace/stats"
)

const (
	statsBucketDuration int64 = 1e10 // 10 seconds
)

// ComputeAPMStats calculates the stats that should be submitted to APM about a given trace
func ComputeAPMStats(tracePayload *pb.TracePayload) *stats.Payload {

	statsRawBuckets := make(map[int64]*stats.RawBucket)

	for _, trace := range tracePayload.Traces {
		spans := GetAnalyzedSpans(trace.Spans)

		sublayers := stats.ComputeSublayers(trace.Spans)
		for _, span := range spans {

			// Aggregate the span to a bucket by rounding its end timestamp to the closest bucket ts.
			// E.g., for buckets of size 10, a span ends on 36 should be aggregated to the second bucket
			// with bucketTS 30 (36 - 36 % 10). Create a new bucket if needed.
			spanEnd := span.Start + span.Duration
			bucketTS := spanEnd - (spanEnd % statsBucketDuration)
			var statsRawBucket *stats.RawBucket
			if existingBucket, ok := statsRawBuckets[bucketTS]; ok {
				statsRawBucket = existingBucket
			} else {
				statsRawBucket = stats.NewRawBucket(bucketTS, statsBucketDuration)
				statsRawBuckets[bucketTS] = statsRawBucket
			}

			// Use weight 1, as xray sampling is not uniform, and its rate is unknown to us.
			// In fact, for "low volume" Lambda functions, the sampling rate is typically 100%.
			// TopLevel is always "true" since we only compute stats for top-level spans.
			weightedSpan := &stats.WeightedSpan{
				Span:     span,
				Weight:   1,
				TopLevel: true,
			}
			statsRawBucket.HandleSpan(weightedSpan, tracePayload.Env, []string{}, sublayers)
		}
	}

	// Export statsRawBuckets to statsBuckets
	statsBuckets := make([]stats.Bucket, 0)
	for _, statsRawBucket := range statsRawBuckets {
		statsBuckets = append(statsBuckets, statsRawBucket.Export())
	}
	return &stats.Payload{
		HostName: tracePayload.HostName,
		Env:      tracePayload.Env,
		Stats:    statsBuckets,
	}
}
