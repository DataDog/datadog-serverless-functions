// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"bufio"
	"bytes"
	"compress/gzip"
	"fmt"
	"io"
)

var gzipMagic = []byte{0x1f, 0x8b}

func gunzip(r io.Reader) (io.Reader, func() error, error) {
	buf := bufio.NewReaderSize(r, len(gzipMagic))
	header, err := buf.Peek(len(gzipMagic))
	if err != nil || !bytes.Equal(header, gzipMagic) {
		return buf, func() error { return nil }, nil
	}

	gz, err := gzip.NewReader(buf)
	if err != nil {
		return nil, nil, fmt.Errorf("gzip: %w", err)
	}
	return gz, func() error { return gz.Close() }, nil
}

func flattenByKey(src map[string]any, field, keyField, outputField string, alwaysWrite bool) {
	arr, ok := src[field].([]any)
	if !ok && !alwaysWrite {
		return
	}

	result := make(map[string]any, len(arr))
	for _, item := range arr {
		obj, ok := item.(map[string]any)
		if !ok {
			continue
		}

		key, _ := obj[keyField].(string)
		if key == "" {
			continue
		}
		delete(obj, keyField)
		result[key] = obj
	}

	out := field
	if outputField != "" {
		delete(src, field)
		out = outputField
	}
	src[out] = result
}
