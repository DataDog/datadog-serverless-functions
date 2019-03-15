// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2019 Datadog, Inc.

var DD_API_KEY = process.env.DD_API_KEY || '<DATADOG_API_KEY>';
var DD_URL = process.env.DD_URL || 'functions-intake.logs.datadoghq.com';
var DD_TAGS = process.env.DD_TAGS || '<TAG_KEY>:<TAG_VALUE>';
var DD_PORT = process.env.DD_PORT || 10516;
var DD_SERVICE = process.env.DD_SERVICE || 'azure';
var DD_SOURCE = process.env.DD_SOURCE || 'azure';
var DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';

module.exports = {
  DD_API_KEY,
  DD_URL,
  DD_TAGS,
  DD_PORT,
  DD_SERVICE,
  DD_SOURCE,
  DD_SOURCE_CATEGORY
}
