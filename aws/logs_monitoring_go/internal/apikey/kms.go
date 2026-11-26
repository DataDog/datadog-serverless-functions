// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import (
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"strings"
	"unicode/utf8"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/sdkclient"
	"github.com/aws/aws-sdk-go-v2/service/kms"
)

type KMSAPIKeySource struct {
	Client     sdkclient.KMS
	Ciphertext string
}

func (ks *KMSAPIKeySource) Get(ctx context.Context) (APIKey, error) {
	decoded, err := base64.StdEncoding.DecodeString(ks.Ciphertext)
	if err != nil {
		return "", fmt.Errorf("base64-decode ciphertext: %w", err)
	}

	out, err := ks.Client.Decrypt(ctx, &kms.DecryptInput{
		CiphertextBlob: decoded,
	})
	if err != nil {
		return "", fmt.Errorf("decrypt KMS ciphertext: %w", err)
	}

	if out.Plaintext == nil {
		return "", errors.New("KMS decryption returned no plaintext")
	}

	if !utf8.Valid(out.Plaintext) {
		return APIKey(base64.StdEncoding.EncodeToString(out.Plaintext)), nil
	}

	return APIKey(strings.TrimSpace(string(out.Plaintext))), nil
}
