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
	"sync"
)

const (
	cloudTrailARNKey          = "arn"
	cloudTrailUserIdentityKey = "userIdentity"
)

var cloudTrailRegex = sync.OnceValue(func() *regexp.Regexp {
	return regexp.MustCompile(`\d+_CloudTrail(|-Digest|-Insight)_\w{2}(|-gov|-cn)-\w{4,9}-\d_(|.+)\d{8}T\d{4,6}Z(|.+)\.json\.gz$`)
})

var ec2InstanceRegexp = sync.OnceValue(func() *regexp.Regexp {
	return regexp.MustCompile(`^arn:aws:sts::.*?:assumed-role/(?P<role>.*?)/(?P<host>i-([0-9a-f]{8}|[0-9a-f]{17}))$`)
})

func decodeCloudTrail(r io.Reader) iter.Seq2[s3Record, error] {
	return func(yield func(s3Record, error) bool) {
		gz, err := gzip.NewReader(r)
		if err != nil {
			yield(s3Record{}, fmt.Errorf("decode cloudtrail gzip: %w", err))
			return
		}
		defer gz.Close() //nolint:errcheck

		dec := json.NewDecoder(gz)

		if t, err := dec.Token(); err != nil || t != json.Delim('{') {
			yield(s3Record{}, errors.New("decode cloudtrail: expected '{' at start of JSON"))
			return
		}
		if t, err := dec.Token(); err != nil || t != "Records" {
			yield(s3Record{}, errors.New("decode cloudtrail: expected 'Records' key"))
			return
		}
		if t, err := dec.Token(); err != nil || t != json.Delim('[') {
			yield(s3Record{}, errors.New("decode cloudtrail: expected '[' at start of Records array"))
			return
		}

		for dec.More() {
			var record map[string]any
			if err := dec.Decode(&record); err != nil {
				yield(s3Record{}, fmt.Errorf("decode cloudtrail record: %w", err))
				return
			}

			msg, err := json.Marshal(record)
			if err != nil {
				yield(s3Record{}, fmt.Errorf("marshal cloudtrail record: %w", err))
				return
			}

			host := cloudtrailHost(record)
			if !yield(s3Record{Message: string(msg), Host: host}, nil) {
				return
			}
		}
	}
}

func cloudtrailHostFromMessage(message string) string {
	var record map[string]any
	if err := json.Unmarshal([]byte(message), &record); err != nil {
		return ""
	}
	return cloudtrailHost(record)
}

func cloudtrailHost(record map[string]any) string {
	ui, ok := record[cloudTrailUserIdentityKey].(map[string]any)
	if !ok {
		slog.Debug(cloudTrailUserIdentityKey + " key not found, cloudtrail host extraction skipped")
		return ""
	}
	arn, ok := ui[cloudTrailARNKey].(string)
	if !ok {
		slog.Debug(cloudTrailARNKey + " key not found, cloudtrail host extraction skipped")
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
