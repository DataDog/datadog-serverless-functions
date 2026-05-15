// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"compress/gzip"
	"encoding/json"
	"fmt"
	"io"
	"iter"
	"log/slog"
	"regexp"
	"strings"

	"github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go/internal/parsing"
)

const (
	cloudTrailARNKey          = "arn"
	cloudTrailUserIdentityKey = "userIdentity"
)

var (
	cloudTrailRegex   = regexp.MustCompile(`\d+_CloudTrail(|-Digest|-Insight)_\w{2}(|-gov|-cn)-\w{4,9}-\d_(|.+)\d{8}T\d{4,6}Z(|.+)\.json\.gz$`)
	ec2InstanceRegexp = regexp.MustCompile(`^arn:aws:sts::.*?:assumed-role/(?P<role>.*?)/(?P<host>i-([0-9a-f]{8}|[0-9a-f]{17}))$`)
)

func decodeCloudTrail(r io.Reader) iter.Seq2[string, error] {
	return func(yield func(string, error) bool) {
		gz, err := gzip.NewReader(r)
		if err != nil {
			yield("", fmt.Errorf("gzip: %w", err))
			return
		}
		defer gz.Close() //nolint:errcheck

		dec := json.NewDecoder(gz)
		if err := parsing.SkipToRecords(dec); err != nil {
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

func cloudtrailHost(message string) (host string) {
	dec := json.NewDecoder(strings.NewReader(message))
	if err := parsing.SkipBrace(dec); err != nil {
		return
	}

	if err := parsing.SkipToKey(dec, "userIdentity"); err != nil {
		return
	}

	if err := parsing.SkipBrace(dec); err != nil {
		return
	}

	if err := parsing.SkipToKey(dec, "arn"); err != nil {
		return
	}

	var arn string
	if err := dec.Decode(&arn); err != nil {
		return
	}

	matches := ec2InstanceRegexp.FindStringSubmatch(arn)
	if matches != nil {
		host = matches[ec2InstanceRegexp.SubexpIndex("host")]
		slog.Debug("ec2 host found in userIdentity.arn")
	}
	return
}
