// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"compress/gzip"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"iter"
	"log/slog"
	"regexp"
	"strings"
	"sync"
)

const (
	cloudTrailARNKey          = "arn"
	cloudTrailUserIdentityKey = "userIdentity"
)

var cloudTrailRegex = regexp.MustCompile(`\d+_CloudTrail(|-Digest|-Insight)_\w{2}(|-gov|-cn)-\w{4,9}-\d_(|.+)\d{8}T\d{4,6}Z(|.+)\.json\.gz$`)

var ec2InstanceRegexp = sync.OnceValue(func() *regexp.Regexp {
	return regexp.MustCompile(`^arn:aws:sts::.*?:assumed-role/(?P<role>.*?)/(?P<host>i-([0-9a-f]{8}|[0-9a-f]{17}))$`)
})

func decodeCloudTrail(r io.Reader) iter.Seq2[string, error] {
	return func(yield func(string, error) bool) {
		gz, err := gzip.NewReader(r)
		if err != nil {
			yield("", fmt.Errorf("decode cloudtrail gzip: %w", err))
			return
		}
		defer gz.Close() //nolint:errcheck

		dec := json.NewDecoder(gz)

		if t, err := dec.Token(); err != nil || t != json.Delim('{') {
			yield("", errors.New("decode cloudtrail: expected '{' at start of JSON"))
			return
		}
		if t, err := dec.Token(); err != nil || t != "Records" {
			yield("", errors.New("decode cloudtrail: expected 'Records' key"))
			return
		}
		if t, err := dec.Token(); err != nil || t != json.Delim('[') {
			yield("", errors.New("decode cloudtrail: expected '[' at start of Records array"))
			return
		}

		for dec.More() {
			var raw json.RawMessage
			if err := dec.Decode(&raw); err != nil {
				yield("", fmt.Errorf("decode cloudtrail record: %w", err))
				return
			}
			if !yield(string(raw), nil) {
				return
			}
		}
	}
}

func cloudtrailHost(message string) string {
	dec := json.NewDecoder(strings.NewReader(message))
	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return ""
	}

	for dec.More() {
		key, err := dec.Token()
		if err != nil {
			return ""
		}
		if key != cloudTrailUserIdentityKey {
			var skip json.RawMessage
			if err := dec.Decode(&skip); err != nil {
				return ""
			}
			continue
		}

		if t, err := dec.Token(); err != nil || t != json.Delim('{') {
			return ""
		}

		for dec.More() {
			innerKey, err := dec.Token()
			if err != nil {
				return ""
			}
			if innerKey != cloudTrailARNKey {
				var skip json.RawMessage
				if err := dec.Decode(&skip); err != nil {
					return ""
				}
				continue
			}

			var arn string
			if err := dec.Decode(&arn); err != nil {
				return ""
			}

			re := ec2InstanceRegexp()
			matches := re.FindStringSubmatch(arn)
			if matches == nil {
				slog.Debug(arn + " arn did not match an EC2 host instance, cloudtrail host extraction skipped")
				return ""
			}
			return matches[re.SubexpIndex("host")]
		}
		return ""
	}
	return ""
}
