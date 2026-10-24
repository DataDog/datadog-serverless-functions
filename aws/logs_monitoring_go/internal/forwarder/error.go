// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarder

import (
	"errors"
	"fmt"
	"net/http"
)

type SendError struct {
	Err       error
	Stored    bool
	Permanent bool
}

func (e *SendError) Error() string {
	return fmt.Sprintf("send to intake: %v (stored for retry: %t, permanent: %t)", e.Err, e.Stored, e.Permanent)
}

func (e *SendError) Unwrap() error {
	return e.Err
}

type intakeError struct {
	status int
	body   string
}

func (e *intakeError) Error() string {
	if e.body == "" {
		return fmt.Sprintf("intake (http/%d)", e.status)
	}
	return fmt.Sprintf("intake (http/%d): %s", e.status, e.body)
}

func isPermanent(err error) bool {
	var intake *intakeError
	if !errors.As(err, &intake) {
		return false
	}

	return intake.status == http.StatusBadRequest || intake.status == http.StatusRequestEntityTooLarge
}
