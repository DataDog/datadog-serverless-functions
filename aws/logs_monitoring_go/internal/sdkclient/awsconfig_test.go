// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

import (
	"crypto/fips140"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/stretchr/testify/require"
)

func TestFipsLoadOption(t *testing.T) {
	var options awsconfig.LoadOptions
	require.NoError(t, fipsLoadOption()(&options))

	want := aws.FIPSEndpointStateUnset
	if fips140.Enabled() {
		want = aws.FIPSEndpointStateEnabled
	}
	require.Equal(t, want, options.UseFIPSEndpoint)
}
