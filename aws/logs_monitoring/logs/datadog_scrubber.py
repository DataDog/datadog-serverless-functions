# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2021 Datadog, Inc.


import os
from logs.exceptions import ScrubbingException
from logs.helpers import compileRegex


class DatadogScrubber(object):
    def __init__(self, configs):
        rules = []
        for config in configs:
            if config.name in os.environ:
                rules.append(
                    ScrubbingRule(
                        compileRegex(config.name, config.pattern),
                        config.placeholder,
                        config.enabled,
                    )
                )
        self._rules = rules

    def scrub(self, payload):
        for rule in self._rules:
            if rule.enabled is False:
                continue
            try:
                payload = rule.regex.sub(rule.placeholder, payload)
            except Exception:
                raise ScrubbingException()
        return payload


class ScrubbingRule(object):
    def __init__(self, regex, placeholder, enabled):
        self.regex = regex
        self.placeholder = placeholder
        self.enabled = enabled
