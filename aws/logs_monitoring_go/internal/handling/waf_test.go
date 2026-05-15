// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2026-Present Datadog, Inc.

package handling

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestFlattenWAFMessage(t *testing.T) {
	t.Parallel()

	tests := map[string]struct {
		input string
		want  string
	}{
		"headers": {
			input: `{"httpRequest":{"headers":[{"name":"header1","value":"value1"},{"name":"header2","value":"value2"}]}}`,
			want:  `{"httpRequest":{"headers":{"header1":"value1","header2":"value2"}}}`,
		},
		"nonTerminatingMatchingRules": {
			input: `{"nonTerminatingMatchingRules":[{"ruleId":"nonterminating1","action":"COUNT"},{"ruleId":"nonterminating2","action":"COUNT"}]}`,
			want:  `{"nonTerminatingMatchingRules":{"nonterminating1":{"action":"COUNT"},"nonterminating2":{"action":"COUNT"}}}`,
		},
		"rateBasedRuleList": {
			input: `{"rateBasedRuleList":[{"limitValue":"195.154.122.189","rateBasedRuleName":"tf-rate-limit-5-min","rateBasedRuleId":"arn:aws:wafv2:ap-southeast-2:068133125972","maxRateAllowed":300,"limitKey":"IP"},{"limitValue":"195.154.122.189","rateBasedRuleName":"no-rate-limit","rateBasedRuleId":"arn:aws:wafv2:ap-southeast-2:068133125972","maxRateAllowed":300,"limitKey":"IP"}]}`,
			want:  `{"rateBasedRuleList":{"tf-rate-limit-5-min":{"limitValue":"195.154.122.189","rateBasedRuleId":"arn:aws:wafv2:ap-southeast-2:068133125972","maxRateAllowed":300,"limitKey":"IP"},"no-rate-limit":{"limitValue":"195.154.122.189","rateBasedRuleId":"arn:aws:wafv2:ap-southeast-2:068133125972","maxRateAllowed":300,"limitKey":"IP"}}}`,
		},
		"ruleGroupList with all sub-fields": {
			input: `{"ruleGroupList":[{"ruleGroupId":"AWS#AWSManagedRulesSQLiRuleSet","terminatingRule":{"ruleId":"SQLi_QUERYARGUMENTS","action":"BLOCK"},"nonTerminatingMatchingRules":[{"exclusionType":"REGULAR","ruleId":"first_nonterminating"},{"exclusionType":"REGULAR","ruleId":"second_nonterminating"}],"excludedRules":[{"exclusionType":"EXCLUDED_AS_COUNT","ruleId":"GenericRFI_BODY"},{"exclusionType":"EXCLUDED_AS_COUNT","ruleId":"second_exclude"}]}]}`,
			want:  `{"ruleGroupList":{"AWS#AWSManagedRulesSQLiRuleSet":{"terminatingRule":{"SQLi_QUERYARGUMENTS":{"action":"BLOCK"}},"nonTerminatingMatchingRules":{"first_nonterminating":{"exclusionType":"REGULAR"},"second_nonterminating":{"exclusionType":"REGULAR"}},"excludedRules":{"GenericRFI_BODY":{"exclusionType":"EXCLUDED_AS_COUNT"},"second_exclude":{"exclusionType":"EXCLUDED_AS_COUNT"}}}}}`,
		},
		"ruleGroupList with two rules same group id": {
			input: `{"ruleGroupList":[{"ruleGroupId":"AWS#AWSManagedRulesSQLiRuleSet","terminatingRule":{"ruleId":"SQLi_QUERYARGUMENTS","action":"BLOCK"}},{"ruleGroupId":"AWS#AWSManagedRulesSQLiRuleSet","terminatingRule":{"ruleId":"secondRULE","action":"BLOCK"}}]}`,
			want:  `{"ruleGroupList":{"AWS#AWSManagedRulesSQLiRuleSet":{"terminatingRule":{"SQLi_QUERYARGUMENTS":{"action":"BLOCK"},"secondRULE":{"action":"BLOCK"}}}}}`,
		},
		"ruleGroupList with three rules two group ids": {
			input: `{"ruleGroupList":[{"ruleGroupId":"AWS#AWSManagedRulesSQLiRuleSet","terminatingRule":{"ruleId":"SQLi_QUERYARGUMENTS","action":"BLOCK"}},{"ruleGroupId":"AWS#AWSManagedRulesSQLiRuleSet","terminatingRule":{"ruleId":"secondRULE","action":"BLOCK"}},{"ruleGroupId":"A_DIFFERENT_ID","terminatingRule":{"ruleId":"thirdRULE","action":"BLOCK"}}]}`,
			want:  `{"ruleGroupList":{"AWS#AWSManagedRulesSQLiRuleSet":{"terminatingRule":{"SQLi_QUERYARGUMENTS":{"action":"BLOCK"},"secondRULE":{"action":"BLOCK"}}},"A_DIFFERENT_ID":{"terminatingRule":{"thirdRULE":{"action":"BLOCK"}}}}}`,
		},
		"no waf fields": {
			input: `{"timestamp":123,"action":"ALLOW"}`,
			want:  `{"timestamp":123,"action":"ALLOW"}`,
		},
	}

	for name, tc := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			got := flattenWAFMessage(tc.input)
			assert.JSONEq(t, tc.want, got)
		})
	}
}

func TestFlattenWAFMessagePassthrough(t *testing.T) {
	t.Parallel()

	tests := map[string]string{
		"invalid json": "not json at all",
		"empty string": "",
	}

	for name, input := range tests {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			assert.Equal(t, input, flattenWAFMessage(input))
		})
	}
}
