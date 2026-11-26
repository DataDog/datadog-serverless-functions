// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"bytes"
	"context"
	"crypto/fips140"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/httpclient"
	"github.com/aws/aws-sdk-go-v2/aws"
	v4 "github.com/aws/aws-sdk-go-v2/aws/signer/v4"
)

const (
	stsService          = "sts"
	getCallerIdentity   = "Action=GetCallerIdentity&Version=2011-06-15"
	orgIDHeader         = "x-ddog-org-id"
	intakeKeyTimeout    = 15 * time.Second
	maximumResponseSize = 1 << 20 // 1 MiB
)

type WorkloadIdentityFederationAPIKeySource struct {
	signer      *v4.Signer
	region      string
	orgUUID     string
	url         string
	client      *http.Client
	credentials aws.CredentialsProvider
}

func NewWorkloadIdentityFederationAPIKeySource(region, orgUUID, url string, client *http.Client, credentials aws.CredentialsProvider) *WorkloadIdentityFederationAPIKeySource {
	return &WorkloadIdentityFederationAPIKeySource{
		signer:      v4.NewSigner(),
		region:      region,
		orgUUID:     orgUUID,
		url:         url,
		client:      client,
		credentials: credentials,
	}
}

func (ks *WorkloadIdentityFederationAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	creds, err := ks.credentials.Retrieve(ctx)
	if err != nil {
		return "", fmt.Errorf("retrieve credentials: %w", err)
	}

	proof, err := ks.generateProof(ctx, creds, ks.region)
	if err != nil {
		return "", fmt.Errorf("generate proof: %w", err)
	}

	return ks.exchangeProof(ctx, proof)
}

func (ks *WorkloadIdentityFederationAPIKeySource) generateProof(ctx context.Context, credentials aws.Credentials, region string) (string, error) {
	host := "sts." + region + ".amazonaws.com"
	if fips140.Enabled() {
		host = "sts-fips." + region + ".amazonaws.com"
	}
	url := "https://" + host

	body := []byte(getCallerIdentity)
	hash := sha256.Sum256(body)
	payloadHash := hex.EncodeToString(hash[:])

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")
	req.Header.Set(orgIDHeader, ks.orgUUID)
	req.Host = host

	if err := ks.signer.SignHTTP(ctx, credentials, req, payloadHash, stsService, region, time.Now()); err != nil {
		return "", fmt.Errorf("sign request: %w", err)
	}

	headers := req.Header.Clone()
	headers.Set("Host", host)

	headersJSON, err := json.Marshal(headers)
	if err != nil {
		return "", fmt.Errorf("marshal headers: %w", err)
	}

	parts := []string{
		base64.StdEncoding.EncodeToString(body),
		base64.StdEncoding.EncodeToString(headersJSON),
		http.MethodPost,
		base64.StdEncoding.EncodeToString([]byte(url)),
	}
	return strings.Join(parts, "|"), nil
}

type intakeKeyResponse struct {
	Data struct {
		Attributes struct {
			APIKey string `json:"api_key"`
		} `json:"attributes"`
	} `json:"data"`
}

func (ks *WorkloadIdentityFederationAPIKeySource) exchangeProof(ctx context.Context, proof string) (APIKey, error) {
	ctx, cancel := context.WithTimeout(ctx, intakeKeyTimeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, ks.url, http.NoBody)
	if err != nil {
		return "", fmt.Errorf("new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Delegated "+proof)

	resp, err := ks.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("do request: %w", err)
	}
	defer httpclient.DrainClose(resp)

	body, err := io.ReadAll(io.LimitReader(resp.Body, maximumResponseSize+1))
	if err != nil {
		return "", fmt.Errorf("read body: %w", err)
	}
	if len(body) > maximumResponseSize {
		return "", errors.New("delegated API key response exceeds 1 MiB")
	}

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("http %d%s", resp.StatusCode, parseError(body))
	}

	var parsed intakeKeyResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return "", fmt.Errorf("unmarshal: %w", err)
	}
	if parsed.Data.Attributes.APIKey == "" {
		return "", errors.New("API key is empty")
	}

	return APIKey(parsed.Data.Attributes.APIKey), nil
}

type intakeKeyErrorResponse struct {
	Errors []struct {
		Detail string `json:"detail"`
	} `json:"errors"`
}

func parseError(body []byte) string {
	var parsed intakeKeyErrorResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return ""
	}

	var messages []string
	for _, e := range parsed.Errors {
		if e.Detail != "" {
			messages = append(messages, e.Detail)
		}
	}
	if len(messages) == 0 {
		return ""
	}
	return ": " + strings.Join(messages, "; ")
}
