// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package parsing

import (
	"bufio"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestSplit(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		input string
		want  []string
	}{
		"empty_string":      {input: "", want: nil},
		"plain_string":      {input: "hello", want: []string{"hello"}},
		"new_lines":         {input: "a\nb\nc", want: []string{"a", "b", "c"}},
		"trailing_new_line": {input: "a\nb\n", want: []string{"a", "b"}},
		"crlf":              {input: "a\r\nb\r\nc", want: []string{"a", "b", "c"}},
		"form_feed":         {input: "a\fb\fc", want: []string{"a", "b", "c"}},
		"mixed_delimiters":  {input: "a\r\n\fb", want: []string{"a", "b"}},
		"only_delimiters":   {input: "\n\r\f", want: nil},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			scanner := bufio.NewScanner(strings.NewReader(tc.input))
			scanner.Split(split)

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
