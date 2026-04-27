// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package model

type S3Metadata struct {
	LambdaOrigin
	Origin S3Origin `json:"s3"`
}

type S3Origin struct {
	Bucket string `json:"bucket"`
	Key    string `json:"key"`
}
