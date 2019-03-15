// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2019 Datadog, Inc.

const STRING = 'string';  // example: 'some message'
const STRING_ARRAY = 'string-array';  // example: ['one message', 'two message', ...]
const JSON_OBJECT = 'json-object';  // example: {"key": "value"}
const JSON_RECORDS = 'json-records';  // example: [{"records": [{}, {}, ...]}, {"records": [{}, {}, ...]}, ...]
const JSON_ARRAY = 'json-array';  // example: [{"key": "value"}, {"key": "value"}, ...]
const INVALID = 'invalid';

module.exports = {
  STRING,
  STRING_ARRAY,
  JSON_OBJECT,
  JSON_RECORDS,
  JSON_ARRAY,
  INVALID
}
