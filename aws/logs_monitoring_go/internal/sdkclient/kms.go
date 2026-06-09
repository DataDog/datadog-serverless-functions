// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

//go:generate go tool mockgen -source=kms.go -package=sdkclient -destination=kms_mockgen.go

import (
	"context"
	"encoding/base64"
	"fmt"
	"strings"
	"sync"

	"github.com/aws/aws-sdk-go-v2/service/kms"
)

type KMS interface {
	Decrypt(ctx context.Context, params *kms.DecryptInput, optFns ...func(*kms.Options)) (*kms.DecryptOutput, error)
}

var getKMS = sync.OnceValues(func() (KMS, error) {
	cfg, err := AWSConfig()
	if err != nil {
		return nil, err
	}
	return kms.NewFromConfig(cfg), nil
})

func ResolveFromKMS(ctx context.Context, ciphertext string) (string, error) {
	kmsClient, err := getKMS()
	if err != nil {
		return "", err
	}
	return DecryptKMSCiphertext(ctx, kmsClient, ciphertext)
}

func DecryptKMSCiphertext(ctx context.Context, kmsClient KMS, ciphertext string) (string, error) {
	decoded, err := base64.StdEncoding.DecodeString(ciphertext)
	if err != nil {
		return "", fmt.Errorf("base64-decoding ciphertext: %w", err)
	}

	result, err := kmsClient.Decrypt(ctx, &kms.DecryptInput{
		CiphertextBlob: decoded,
	})
	if err != nil {
		return "", fmt.Errorf("decrypting KMS ciphertext: %w", err)
	}

	if result.Plaintext == nil {
		return "", fmt.Errorf("KMS decryption returned no plaintext")
	}

	return strings.TrimSpace(string(result.Plaintext)), nil
}
