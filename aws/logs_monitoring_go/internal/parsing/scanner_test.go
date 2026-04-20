// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

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
		rg    *regexp.Regexp
		want  []string
	}{
		"lines_empty_string":        {input: "", rg: nil, want: nil},
		"lines_plain_string":        {input: "hello", rg: nil, want: []string{"hello"}},
		"lines_plain_string_spaces": {input: "hello world !", rg: nil, want: []string{"hello world !"}},
		"lines_new_lines":           {input: "a\nb\nc", rg: nil, want: []string{"a", "b", "c"}},
		"lines_trailing_new_line":   {input: "a\nb\n", rg: nil, want: []string{"a", "b"}},
		"lines_crlf":                {input: "a\r\nb\r\nc", rg: nil, want: []string{"a", "b", "c"}},
		"lines_form_feed":           {input: "a\fb\fc", rg: nil, want: []string{"a", "b", "c"}},
		"lines_mixed_delimiters":    {input: "a\r\n\fb", rg: nil, want: []string{"a", "b"}},
		"lines_only_delimiters":     {input: "\n\r\f", rg: nil, want: nil},

		"regex_empty":                     {input: "", rg: dateRegex, want: nil},
		"regex_not_matching_at_start":     {input: "ERROR something2024-01-15 ERROR something", rg: dateRegex, want: []string{"ERROR something", "2024-01-15 ERROR something"}},
		"regex_single_entry":              {input: "2024-01-15 ERROR something", rg: dateRegex, want: []string{"2024-01-15 ERROR something"}},
		"regex_two_entries_with_newline":  {input: "2024-01-15 ERROR\n2024-01-16 INFO", rg: dateRegex, want: []string{"2024-01-15 ERROR\n", "2024-01-16 INFO"}},
		"regex_continuation_lines":        {input: "2024-01-15 ERROR\n    at com.foo\n2024-01-16 INFO", rg: dateRegex, want: []string{"2024-01-15 ERROR\n    at com.foo\n", "2024-01-16 INFO"}},
		"regex_multiple_matches_one_line": {input: "2024-01-15 ERROR2024-01-16 INFO", rg: dateRegex, want: []string{"2024-01-15 ERROR", "2024-01-16 INFO"}},
		"regex_three_matches_one_line":    {input: "2024-01-15 A2024-01-16 B2024-01-17 C", rg: dateRegex, want: []string{"2024-01-15 A", "2024-01-16 B", "2024-01-17 C"}},
		"regex_empty_string":              {input: "", rg: dateRegex, want: nil},
		"regex_no_match":                  {input: "hello world", rg: dateRegex, want: []string{"hello world"}},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			scanner := NewScanner(strings.NewReader(tc.input), tc.rg)

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
		rg *regexp.Regexp
	}{
		"lines": {rg: nil},
		"regex": {rg: regexp.MustCompile(`\d{4}-\d{2}-\d{2}`)},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			scanner := NewScanner(strings.NewReader(oversized), tc.rg)

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
