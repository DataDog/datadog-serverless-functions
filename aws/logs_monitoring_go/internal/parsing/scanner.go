// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bufio"
	"bytes"
	"io"
	"regexp"
)

const maxTokenSize = 512 * 1024

type Scanner struct {
	*bufio.Scanner
	rg *regexp.Regexp
}

func NewScanner(r io.Reader, rg *regexp.Regexp) *Scanner {
	s := &Scanner{
		Scanner: bufio.NewScanner(r),
		rg:      rg,
	}

	s.Buffer(make([]byte, 0, bufio.MaxScanTokenSize), maxTokenSize)

	if rg != nil {
		s.Split(s.splitOnRegex)
	} else {
		s.Split(s.splitOnLines)
	}

	return s
}

func (s *Scanner) splitOnRegex(data []byte, atEOF bool) (advance int, token []byte, err error) {
	if len(data) == 0 {
		return 0, nil, nil
	}

	loc := s.rg.FindIndex(data[1:])
	if loc != nil {
		splitAt := loc[0] + 1
		return splitAt, data[:splitAt], nil
	}

	if atEOF || len(data) >= maxTokenSize {
		return len(data), data, nil
	}

	return 0, nil, nil
}

func (s *Scanner) splitOnLines(data []byte, atEOF bool) (advance int, token []byte, err error) {
	if len(data) == 0 {
		return 0, nil, nil
	}

	if i := bytes.IndexAny(data, "\n\r\f"); i >= 0 {
		j := i
		for j < len(data) && (data[j] == '\n' || data[j] == '\r' || data[j] == '\f') {
			j++
		}
		return j, data[:i], nil
	}

	if atEOF || len(data) >= maxTokenSize {
		return len(data), data, nil
	}

	return 0, nil, nil
}
