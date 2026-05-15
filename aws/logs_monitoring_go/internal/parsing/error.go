// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"errors"
	"fmt"
)

var errUnknownEvent = errors.New("unknown event")

type KeyNotFoundError struct {
	Key string
}

func (e *KeyNotFoundError) Error() string {
	return fmt.Sprintf("%s key not found", e.Key)
}

func (e *KeyNotFoundError) Is(target error) bool {
	_, ok := target.(*KeyNotFoundError)
	return ok
}
