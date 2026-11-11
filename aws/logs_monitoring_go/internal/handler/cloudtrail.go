// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handler

import (
	"encoding/json/jsontext"
	"encoding/json/v2"
	"fmt"
	"io"
	"iter"
	"regexp"
)

var (
	cloudTrailRegex   = regexp.MustCompile(`\d+_CloudTrail(|-Digest|-Insight)_\w{2}(|-gov|-cn)-\w{4,9}-\d_(|.+)\d{8}T\d{4,6}Z(|.+)\.json\.gz$`)
	ec2InstanceRegexp = regexp.MustCompile(`^arn:(?:aws|aws-cn|aws-us-gov|aws-iso|aws-iso-b):sts::.*?:assumed-role/(?P<role>.*?)/(?P<host>i-([0-9a-f]{8}|[0-9a-f]{17}))$`)
)

func decodeCloudTrail(r io.Reader) iter.Seq2[string, error] {
	return func(yield func(string, error) bool) {
		dec := jsontext.NewDecoder(r)

		tok, err := dec.ReadToken()
		if err != nil {
			yield("", err)
			return
		}
		if tok.Kind() != '{' {
			yield("", fmt.Errorf(`expected "{" token, got %q`, tok.String()))
			return
		}

		tok, err = dec.ReadToken()
		if err != nil {
			yield("", err)
			return
		}
		if tok.String() != "Records" {
			yield("", fmt.Errorf(`expected "Records" token, got %q`, tok.String()))
			return
		}

		tok, err = dec.ReadToken()
		if err != nil {
			yield("", err)
			return
		}
		if tok.Kind() != '[' {
			yield("", fmt.Errorf(`expected "[" token, got %q`, tok.String()))
			return
		}

		for dec.PeekKind() != ']' {
			raw, err := dec.ReadValue()
			if err != nil {
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
