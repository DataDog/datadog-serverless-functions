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
		if err := skipToRecords(dec); err != nil {
			yield("", fmt.Errorf("cloudtrail: %w", err))
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

func skipBrace(dec *json.Decoder) error {
	if t, err := dec.Token(); err != nil || t != json.Delim('{') {
		return fmt.Errorf("expected '{': %w", err)
	}
	return nil
}

func skipBracket(dec *json.Decoder) error {
	if t, err := dec.Token(); err != nil || t != json.Delim('[') {
		return fmt.Errorf("expected '[': %w", err)
	}
	return nil
}

func skipToKey(dec *json.Decoder, key string) error {
	for dec.More() {
		k, err := dec.Token()
		if err != nil {
			return err
		}

		if k != key {
			if err := skip(dec); err != nil {
				return err
			}
			continue
		}

		return nil
	}

	return fmt.Errorf("key not found %q", key)
}

func skipToRecords(dec *json.Decoder) error {
	if err := skipBrace(dec); err != nil {
		return err
	}

	if err := skipToKey(dec, "Records"); err != nil {
		return err
	}

	if err := skipBracket(dec); err != nil {
		return err
	}
	return nil
}

func skip(dec *json.Decoder) error {
	var skip json.RawMessage
	if err := dec.Decode(&skip); err != nil {
		return fmt.Errorf("skip: %w", err)
	}
	return nil
}
