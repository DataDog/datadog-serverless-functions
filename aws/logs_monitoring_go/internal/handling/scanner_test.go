// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"regexp"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestScanner(t *testing.T) {
	t.Parallel()

	dateRegex := regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)

	tests := map[string]struct {
		input string
		re    *regexp.Regexp
		want  []string
	}{
		"lines empty string":        {input: "", re: nil, want: nil},
		"lines plain string":        {input: "hello", re: nil, want: []string{"hello"}},
		"lines plain string spaces": {input: "hello world !", re: nil, want: []string{"hello world !"}},
		"lines new lines":           {input: "a\nb\nc", re: nil, want: []string{"a", "b", "c"}},
		"lines trailing new line":   {input: "a\nb\n", re: nil, want: []string{"a", "b"}},
		"lines crlf":                {input: "a\r\nb\r\nc", re: nil, want: []string{"a", "b", "c"}},
		"lines form feed":           {input: "a\fb\fc", re: nil, want: []string{"a", "b", "c"}},
		"lines mixed delimiters":    {input: "a\r\n\fb", re: nil, want: []string{"a", "b"}},
		"lines only delimiters":     {input: "\n\r\f", re: nil, want: nil},

		"regex empty":                     {input: "", re: dateRegex, want: nil},
		"regex not matching at start":     {input: "ERROR something2024-01-15 ERROR something", re: dateRegex, want: []string{"ERROR something", "2024-01-15 ERROR something"}},
		"regex single entry":              {input: "2024-01-15 ERROR something", re: dateRegex, want: []string{"2024-01-15 ERROR something"}},
		"regex two entries with newline":  {input: "2024-01-15 ERROR\n2024-01-16 INFO", re: dateRegex, want: []string{"2024-01-15 ERROR\n", "2024-01-16 INFO"}},
		"regex continuation lines":        {input: "2024-01-15 ERROR\n    at com.foo\n2024-01-16 INFO", re: dateRegex, want: []string{"2024-01-15 ERROR\n    at com.foo\n", "2024-01-16 INFO"}},
		"regex multiple matches one line": {input: "2024-01-15 ERROR2024-01-16 INFO", re: dateRegex, want: []string{"2024-01-15 ERROR", "2024-01-16 INFO"}},
		"regex three matches one line":    {input: "2024-01-15 A2024-01-16 B2024-01-17 C", re: dateRegex, want: []string{"2024-01-15 A", "2024-01-16 B", "2024-01-17 C"}},
		"regex empty string":              {input: "", re: dateRegex, want: nil},
		"regex no match":                  {input: "hello world", re: dateRegex, want: []string{"hello world"}},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			scanner := NewScanner(strings.NewReader(tc.input), tc.re)

			var got []string
			for scanner.Scan() {
				if text := scanner.Text(); text != "" {
					got = append(got, text)
				}
			}

			if err := scanner.Err(); err != nil {
				t.Fatalf("unexpected scanner error: %v", err)
			}

			if diff := cmp.Diff(tc.want, got); diff != "" {
				t.Errorf("mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func TestScannerWithOversizedToken(t *testing.T) {
	t.Parallel()

	overflow := 100
	oversized := strings.Repeat("a", maxTokenSize+overflow)

	tests := map[string]struct {
		re *regexp.Regexp
	}{
		"lines": {re: nil},
		"regex": {re: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			scanner := NewScanner(strings.NewReader(oversized), tc.re)

			var got []string
			for scanner.Scan() {
				got = append(got, scanner.Text())
			}
			if err := scanner.Err(); err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if len(got) != 2 {
				t.Fatalf("want 2 tokens, got %d", len(got))
			}
			if len(got[0]) != maxTokenSize {
				t.Errorf("first token: want %d bytes, got %d", maxTokenSize, len(got[0]))
			}
			if len(got[1]) != overflow {
				t.Errorf("second token: want %d bytes, got %d", overflow, len(got[1]))
			}
		})
	}
}
