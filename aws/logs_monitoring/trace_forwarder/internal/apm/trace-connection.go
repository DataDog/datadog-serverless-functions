/*
 * Unless explicitly stated otherwise all files in this repository are licensed
 * under the Apache License Version 2.0.
 *
 * This product includes software developed at Datadog (https://www.datadoghq.com/).
 * Copyright 2020 Datadog, Inc.
 */
package apm

import (
	"bytes"
	"context"
	"crypto/tls"
	"fmt"
	"net/http"
	"time"

	"github.com/gogo/protobuf/proto"

	"github.com/DataDog/datadog-agent/pkg/trace/pb"
	"github.com/DataDog/datadog-agent/pkg/trace/stats"
)

// TraceEdgeConnection is used to send data to trace edge
type TraceEdgeConnection interface {
	SendTraces(ctx context.Context, trace *pb.TracePayload, maxRetries int) error
	SendStats(ctx context.Context, stats *stats.Payload, maxRetries int) error
}

type traceEdgeConnection struct {
	traceURL           string
	statsURL           string
	apiKey             string
	InsecureSkipVerify bool
}

const (
	traceEdgeTimout        time.Duration = 5 * time.Second
	traceEdgeRetryInterval time.Duration = 1 * time.Second
)

// CreateTraceEdgeConnection returns a new TraceEdgeConnection
func CreateTraceEdgeConnection(rootURL, apiKey string, InsecureSkipVerify bool) TraceEdgeConnection {

	return &traceEdgeConnection{
		traceURL:           rootURL + "/api/v0.2/traces",
		statsURL:           rootURL + "/api/v0.2/stats",
		apiKey:             apiKey,
		InsecureSkipVerify: InsecureSkipVerify,
	}
}

// Payload represents a data payload to be sent to some endpoint
type Payload struct {
	CreationDate time.Time
	Bytes        []byte
	Headers      map[string]string
}

// NewPayload constructs a new payload object with the provided data and with CreationDate initialized to the current
// time.
func NewPayload(bytes []byte, headers map[string]string) *Payload {
	return &Payload{
		CreationDate: time.Now(),
		Bytes:        bytes,
		Headers:      headers,
	}
}

// SendTraces serializes a trace payload to protobuf and sends it to Trace Edge
func (con *traceEdgeConnection) SendTraces(ctx context.Context, trace *pb.TracePayload, maxRetries int) error {
	binary, marshallErr := proto.Marshal(trace)
	if marshallErr != nil {
		return fmt.Errorf("failed to serialize trace payload to protobuf: %v", marshallErr)
	}
	if len(trace.Traces) == 0 {
		return fmt.Errorf("No traces in payload")
	}

	fmt.Printf("Sending trace %d\n", trace.Traces[0].TraceID)

	// Set Headers
	headers := map[string]string{
		"Content-Type":     "application/x-protobuf",
		"Content-Encoding": "identity",
	}

	// Construct a Payload{} from the headers and binary
	payload := Payload{
		CreationDate: time.Now().UTC(),
		Bytes:        binary,
		Headers:      headers,
	}

	var sendErr error
	// If error while sending to trace-edge, retry maximum maxRetries number of times
	// NOTE: APM stores traces by trace id, however, Logs pipeline does NOT dedupe APM events,
	// and retries may potentially cause duplicate APM events in Trace Search
	for retries := 1; retries <= maxRetries; retries++ {
		if sendErr = con.sendPayloadToTraceEdge(ctx, con.apiKey, &payload, con.traceURL, con.InsecureSkipVerify); sendErr == nil {
			return nil
		}
		time.Sleep(traceEdgeRetryInterval)
	}
	return fmt.Errorf("failed to send trace payload to trace edge: %v", sendErr)
}

// SendStats serializes a stats payload to json and sends it to Trace Edge
func (con *traceEdgeConnection) SendStats(ctx context.Context, sts *stats.Payload, maxRetries int) error {
	var b bytes.Buffer
	err := stats.EncodePayload(&b, sts)
	if err != nil {
		return fmt.Errorf("failed to encode stats payload: %v", err)
	}
	binary := b.Bytes()

	// Set Headers
	headers := map[string]string{
		"Content-Type":     "application/json",
		"Content-Encoding": "gzip",
	}

	// Construct a Payload{} from the headers and binary
	payload := Payload{
		CreationDate: time.Now().UTC(),
		Bytes:        binary,
		Headers:      headers,
	}

	var sendErr error
	// If error while sending to trace-edge, retry maximum maxRetries number of times
	// NOTE: APM does NOT dedupe, and retries may potentially cause duplicate/inaccurate stats
	for retries := 1; retries <= maxRetries; retries++ {
		if sendErr = con.sendPayloadToTraceEdge(ctx, con.apiKey, &payload, con.statsURL, con.InsecureSkipVerify); sendErr == nil {
			return nil
		}
		time.Sleep(traceEdgeRetryInterval)
	}
	return fmt.Errorf("failed to send stats payload to trace edge: %v", sendErr)
}

// sendPayloadToTraceEdge sends a payload to Trace Edge
func (con *traceEdgeConnection) sendPayloadToTraceEdge(ctx context.Context, apiKey string, payload *Payload, url string, InsecureSkipVerify bool) error {
	// Create the request to be sent to the API
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(payload.Bytes))
	req = req.WithContext(ctx)

	if err != nil {
		return err
	}

	// userAgent is the computed user agent we'll use when
	// communicating with Datadog
	var userAgent = fmt.Sprintf(
		"%s/%s/%s (+%s)",
		"xray-converter", "0.1", "1", "http://localhost",
	)

	req.Header.Set("DD-Api-Key", apiKey)
	req.Header.Set("User-Agent", userAgent)
	SetExtraHeaders(req.Header, payload.Headers)

	client := NewClient(InsecureSkipVerify)
	resp, err := client.Do(req)

	if err != nil {
		return err
	}
	defer resp.Body.Close()

	// We check the status code to see if the request has succeeded.
	// TODO: define all legit status code and behave accordingly.
	if resp.StatusCode/100 != 2 {
		err := fmt.Errorf("request to %s responded with %s", url, resp.Status)
		if resp.StatusCode/100 == 5 {
			// 5xx errors are retriable
			return err
		}

		// All others aren't
		return err
	}

	// Everything went fine
	return nil
}

// NewClient returns a http.Client configured with the Agent options.
func NewClient(InsecureSkipVerify bool) *http.Client {
	transport := &http.Transport{
		TLSClientConfig: &tls.Config{InsecureSkipVerify: InsecureSkipVerify},
	}

	return &http.Client{Timeout: traceEdgeTimout, Transport: transport}
}

// SetExtraHeaders appends a header map to HTTP headers.
func SetExtraHeaders(h http.Header, extras map[string]string) {
	for key, value := range extras {
		h.Set(key, value)
	}
}
