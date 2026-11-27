// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package apikey

import "net/http"

type AuthRoundTripper struct {
	Source APIKeySource
	Next   http.RoundTripper
}

const authenticationHeader = "DD-API-KEY"

func (rt *AuthRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {
	key, err := rt.Source.Get(req.Context())
	if err != nil {
		return nil, err
	}

	req2 := new(http.Request)
	*req2 = *req
	req2.Header = req.Header.Clone()
	req2.Header.Set(authenticationHeader, string(key))

	resp, err := rt.Next.RoundTrip(req2)
	if resp != nil && (resp.StatusCode == http.StatusUnauthorized || resp.StatusCode == http.StatusForbidden) {
		if i, ok := rt.Source.(Invalidator); ok {
			i.Invalidate()
		}
	}

	return resp, err
}
