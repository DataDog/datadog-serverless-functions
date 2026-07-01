// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package sdkclient

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/service/lambda"
	"github.com/aws/aws-sdk-go-v2/service/lambda/types"
	"github.com/stretchr/testify/require"
	"go.uber.org/mock/gomock"
)

func TestInvokeTargets(t *testing.T) {
	t.Parallel()

	event := json.RawMessage(`{"Records":[{"eventSource":"aws:s3","s3":{"bucket":{"name":"my-bucket"},"object":{"key":"my-key"}}}]}`)

	tests := map[string]struct {
		mockSetup func(m *MockLambda)
		targets   []string
		wantErr   bool
	}{
		"no targets": {
			mockSetup: func(m *MockLambda) {},
			targets:   nil,
		},
		"single target": {
			mockSetup: func(m *MockLambda) {
				m.EXPECT().
					Invoke(gomock.Any(), &lambda.InvokeInput{
						FunctionName:   aws.String("arn:aws:lambda:us-east-1:123456789012:function:first"),
						InvocationType: types.InvocationTypeEvent,
						Payload:        event,
					}).
					Return(&lambda.InvokeOutput{}, nil)
			},
			targets: []string{"arn:aws:lambda:us-east-1:123456789012:function:first"},
		},
		"multiple targets": {
			mockSetup: func(m *MockLambda) {
				m.EXPECT().
					Invoke(gomock.Any(), &lambda.InvokeInput{
						FunctionName:   aws.String("arn:aws:lambda:us-east-1:123456789012:function:first"),
						InvocationType: types.InvocationTypeEvent,
						Payload:        event,
					}).
					Return(&lambda.InvokeOutput{}, nil)
				m.EXPECT().
					Invoke(gomock.Any(), &lambda.InvokeInput{
						FunctionName:   aws.String("arn:aws:lambda:us-east-1:123456789012:function:second"),
						InvocationType: types.InvocationTypeEvent,
						Payload:        event,
					}).
					Return(&lambda.InvokeOutput{}, nil)
			},
			targets: []string{
				"arn:aws:lambda:us-east-1:123456789012:function:first",
				"arn:aws:lambda:us-east-1:123456789012:function:second",
			},
		},
		"error second target": {
			mockSetup: func(m *MockLambda) {
				m.EXPECT().
					Invoke(gomock.Any(), &lambda.InvokeInput{
						FunctionName:   aws.String("arn:aws:lambda:us-east-1:123456789012:function:first"),
						InvocationType: types.InvocationTypeEvent,
						Payload:        event,
					}).
					Return(&lambda.InvokeOutput{}, nil)
				m.EXPECT().
					Invoke(gomock.Any(), &lambda.InvokeInput{
						FunctionName:   aws.String("arn:aws:lambda:us-east-1:123456789012:function:i-do-not-exist"),
						InvocationType: types.InvocationTypeEvent,
						Payload:        event,
					}).
					Return(nil, errors.New("not found"))
			},
			targets: []string{
				"arn:aws:lambda:us-east-1:123456789012:function:first",
				"arn:aws:lambda:us-east-1:123456789012:function:i-do-not-exist",
			},
			wantErr: true,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctrl := gomock.NewController(t)
			mock := NewMockLambda(ctrl)
			tc.mockSetup(mock)

			err := invokeTargets(t.Context(), mock, tc.targets, event)

			if tc.wantErr {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)
		})
	}
}
