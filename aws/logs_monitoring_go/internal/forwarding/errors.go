// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package forwarding

import "fmt"

type PermanentError struct {
	StatusCode int
	Reason     string
}

func (e *PermanentError) Error() string {
	return fmt.Sprintf("intake %d: %s", e.StatusCode, e.Reason)
}
