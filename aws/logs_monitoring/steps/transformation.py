import copy
import json
import logging
import os

from settings import DD_SOURCE

from steps.enums import AwsEventSource

logger = logging.getLogger()
logger.setLevel(logging.getLevelName(os.environ.get("DD_LOG_LEVEL", "INFO").upper()))


def transform(events):
    """Performs transformations on complex events

    Ex: handles special cases with nested arrays of JSON objects
    Args:
        events (dict[]): the list of event dicts we want to transform
    """
    for index, event in enumerate(events):
        waf = parse_aws_waf_logs(event)
        if waf != event:
            events[index] = waf

    for event in reversed(events):
        findings = separate_security_hub_findings(event)

        if findings:
            events.remove(event)
            events.extend(findings)

    return events


def separate_security_hub_findings(event):
    """Replace Security Hub event with series of events based on findings

    Each event should contain one finding only.
    This prevents having an unparsable array of objects in the final log.
    """
    if event.get(DD_SOURCE) != "securityhub" or not event.get("detail", {}).get(
        "findings"
    ):
        return None
    events = []
    event_copy = copy.deepcopy(event)
    # Copy findings before separating
    findings = event_copy.get("detail", {}).get("findings")
    if findings:
        # Remove findings from the original event once we have a copy
        del event_copy["detail"]["findings"]
        # For each finding create a separate log event
        for index, item in enumerate(findings):
            # Copy the original event with source and other metadata
            new_event = copy.deepcopy(event_copy)
            current_finding = findings[index]
            # Get the resources array from the current finding
            resources = current_finding.get("Resources", {})
            new_event["detail"]["finding"] = current_finding
            new_event["detail"]["finding"]["resources"] = {}
            # Separate objects in resources array into distinct attributes
            if resources:
                # Remove from current finding once we have a copy
                del current_finding["Resources"]
                for item in resources:
                    current_resource = item
                    # Capture the type and use it as the distinguishing key
                    resource_type = current_resource.get("Type", {})
                    del current_resource["Type"]
                    new_event["detail"]["finding"]["resources"][
                        resource_type
                    ] = current_resource
            events.append(new_event)
    return events


def parse_aws_waf_logs(event):
    """Parse out complex arrays of objects in AWS WAF logs

    Attributes to convert:
        httpRequest.headers
        nonTerminatingMatchingRules
        rateBasedRuleList
        ruleGroupList

    This prevents having an unparsable array of objects in the final log.
    """
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except json.JSONDecodeError:
            logger.debug("Argument provided for waf parser is not valid JSON")
            return event
    if event.get(DD_SOURCE) != str(AwsEventSource.WAF):
        return event

    event_copy = copy.deepcopy(event)

    message = event_copy.get("message", {})
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            logger.debug(
                "Failed to decode waf message, first bytes were `%s`", message[:8192]
            )
            return event

    headers = message.get("httpRequest", {}).get("headers")
    if headers:
        message["httpRequest"]["headers"] = convert_rule_to_nested_json(headers)

    # Iterate through rules in ruleGroupList and nest them under the group id
    # ruleGroupList has three attributes that need to be handled separately
    rule_groups = message.get("ruleGroupList", {})
    if rule_groups and isinstance(rule_groups, list):
        message["ruleGroupList"] = {}
        for rule_group in rule_groups:
            group_id = None
            if "ruleGroupId" in rule_group and rule_group["ruleGroupId"]:
                group_id = rule_group.pop("ruleGroupId", None)
            if group_id not in message["ruleGroupList"]:
                message["ruleGroupList"][group_id] = {}

            # Extract the terminating rule and nest it under its own id
            if "terminatingRule" in rule_group and rule_group["terminatingRule"]:
                terminating_rule = rule_group.pop("terminatingRule", None)
                if not "terminatingRule" in message["ruleGroupList"][group_id]:
                    message["ruleGroupList"][group_id]["terminatingRule"] = {}
                message["ruleGroupList"][group_id]["terminatingRule"].update(
                    convert_rule_to_nested_json(terminating_rule)
                )

            # Iterate through array of non-terminating rules and nest each under its own id
            if "nonTerminatingMatchingRules" in rule_group and isinstance(
                rule_group["nonTerminatingMatchingRules"], list
            ):
                non_terminating_rules = rule_group.pop(
                    "nonTerminatingMatchingRules", None
                )
                if (
                    "nonTerminatingMatchingRules"
                    not in message["ruleGroupList"][group_id]
                ):
                    message["ruleGroupList"][group_id][
                        "nonTerminatingMatchingRules"
                    ] = {}
                message["ruleGroupList"][group_id][
                    "nonTerminatingMatchingRules"
                ].update(convert_rule_to_nested_json(non_terminating_rules))

            # Iterate through array of excluded rules and nest each under its own id
            if "excludedRules" in rule_group and isinstance(
                rule_group["excludedRules"], list
            ):
                excluded_rules = rule_group.pop("excludedRules", None)
                if "excludedRules" not in message["ruleGroupList"][group_id]:
                    message["ruleGroupList"][group_id]["excludedRules"] = {}
                message["ruleGroupList"][group_id]["excludedRules"].update(
                    convert_rule_to_nested_json(excluded_rules)
                )

    rate_based_rules = message.get("rateBasedRuleList", {})
    if rate_based_rules:
        message["rateBasedRuleList"] = convert_rule_to_nested_json(rate_based_rules)

    non_terminating_rules = message.get("nonTerminatingMatchingRules", {})
    if non_terminating_rules:
        message["nonTerminatingMatchingRules"] = convert_rule_to_nested_json(
            non_terminating_rules
        )

    event_copy["message"] = message
    return event_copy


def convert_rule_to_nested_json(rule):
    key = None
    result_obj = {}
    if not isinstance(rule, list):
        if "ruleId" in rule and rule["ruleId"]:
            key = rule.pop("ruleId", None)
            result_obj.update({key: rule})
            return result_obj
    for entry in rule:
        if "ruleId" in entry and entry["ruleId"]:
            key = entry.pop("ruleId", None)
        elif "rateBasedRuleName" in entry and entry["rateBasedRuleName"]:
            key = entry.pop("rateBasedRuleName", None)
        elif "name" in entry and "value" in entry:
            key = entry["name"]
            entry = entry["value"]
        result_obj.update({key: entry})
    return result_obj
