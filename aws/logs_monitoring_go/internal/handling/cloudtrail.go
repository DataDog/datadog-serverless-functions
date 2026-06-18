// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"encoding/json"
	"fmt"
	"io"
	"iter"
	"regexp"
)

var (
	cloudTrailRegex   = regexp.MustCompile(`\d+_CloudTrail(|-Digest|-Insight)_\w{2}(|-gov|-cn)-\w{4,9}-\d_(|.+)\d{8}T\d{4,6}Z(|.+)\.json\.gz$`)
	ec2InstanceRegexp = regexp.MustCompile(`^arn:aws:sts::.*?:assumed-role/(?P<role>.*?)/(?P<host>i-([0-9a-f]{8}|[0-9a-f]{17}))$`)
)

func decodeCloudTrail(r io.Reader) iter.Seq2[string, error] {
	return func(yield func(string, error) bool) {
		dec := json.NewDecoder(r)
		t, err := dec.Token()
		if err != nil {
			yield("", err)
			return
		}
		if t != json.Delim('{') {
			yield("", fmt.Errorf(`expected "{" token, got %q`, t))
			return
		}

		t, err = dec.Token()
		if err != nil {
			yield("", err)
			return
		}
		if t != "Records" {
			yield("", fmt.Errorf(`expected "Records" token, got %q`, t))
			return
		}

		t, err = dec.Token()
		if err != nil {
			yield("", err)
			return
		}
		if t != json.Delim('[') {
			yield("", fmt.Errorf(`expected "[" token, got %q`, t))
			return
		}

		for dec.More() {
			var raw json.RawMessage
			if err := dec.Decode(&raw); err != nil {
				yield("", fmt.Errorf(`decode: %w`, err))
				return
			}
			if !yield(string(raw), nil) {
				return
			}
		}
	}
}

func cloudtrailHost(message string) string {
	var record struct {
		UserIdentity struct {
			ARN string `json:"arn"`
		} `json:"userIdentity"`
	}
	if err := json.Unmarshal([]byte(message), &record); err != nil {
		return ""
	}

	matches := ec2InstanceRegexp.FindStringSubmatch(record.UserIdentity.ARN)
	if matches != nil {
		return matches[ec2InstanceRegexp.SubexpIndex("host")]
	}
	return ""
}
