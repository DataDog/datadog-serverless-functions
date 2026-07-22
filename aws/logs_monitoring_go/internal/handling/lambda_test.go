// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestLambdaName(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		logGroup  string
		logStream string
		want      string
	}{
		"default log group":                    {logGroup: "/aws/lambda/my-function", logStream: "stream", want: "my-function"},
		"default log group lowercased":         {logGroup: "/aws/lambda/My-Function", logStream: "stream", want: "my-function"},
		"custom log group name from stream":    {logGroup: "/aws/vendedlogs/states/anyLogGroupName", logStream: "2020/03/05/Test-Customized-LogGroup[$LATEST]20bddfd5a2dc4c6b97ac02800eae90d0", want: "test-customized-loggroup"},
		"stream takes priority over log group": {logGroup: "/aws/lambda/from-group", logStream: "2020/03/05/from-stream[$LATEST]20bddfd5a2dc4c6b97ac02800eae90d0", want: "from-stream"},
		"stream without function name":         {logGroup: "my-custom-group", logStream: "2023/11/04/[$LATEST]4426346c2cdf4c54a74d3bd2b929fc44", want: ""},
		"non-lambda log group":                 {logGroup: "/aws/rds/cluster", logStream: "stream", want: ""},
		"empty":                                {logGroup: "", logStream: "", want: ""},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(t, tc.want, lambdaName(tc.logGroup, tc.logStream))
		})
	}
}
