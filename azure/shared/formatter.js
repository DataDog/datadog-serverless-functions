// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2019 Datadog, Inc.

const STRING = require('./constants.js').STRING;
const STRING_ARRAY = require('./constants.js').STRING_ARRAY;
const JSON_OBJECT = require('./constants.js').JSON_OBJECT;
const JSON_RECORDS = require('./constants.js').JSON_RECORDS;
const JSON_ARRAY = require('./constants.js').JSON_ARRAY;
const INVALID = require('./constants.js').INVALID;

const DD_TAGS = require('./env.js').DD_TAGS;
const DD_SERVICE = require('./env.js').DD_SERVICE;
const DD_SOURCE = require('./env.js').DD_SOURCE;
const DD_SOURCE_CATEGORY = require('./env.js').DD_SOURCE_CATEGORY;


module.exports = function handleLogs(handler, logs, context) {
  var logsType = getLogFormat(logs);
  switch (logsType) {
    case STRING:
        handler(addTagsToStringLog)(logs);
        break;
    case JSON_OBJECT:
        handler(addTagsToJsonLog)(logs);
        break;
    case STRING_ARRAY:
        logs.forEach( handler(addTagsToStringLog) );
        break;
    case JSON_RECORDS:
        logs.forEach( message => {
            message.records.forEach( handler(addTagsToJsonLog) );
        });
        break;
    case JSON_ARRAY:
        logs.forEach( handler(addTagsToJsonLog) );
        break;
    case INVALID:
    default:
        context.log.warn('logs format is invalid');
        break;
  }
};

function getLogFormat(logs) {
  if (typeof logs === 'string') {
      return STRING;
  }
  if (!Array.isArray(logs) && typeof logs === 'object' && logs !== null) {
      return JSON_OBJECT;
  }
  if (!Array.isArray(logs)) {
      return INVALID;
  }
  if (typeof logs[0] === 'object') {
      if (logs[0].records !== undefined) {
          return JSON_RECORDS;
      } else {
          return JSON_ARRAY;
      }
  }
  if (typeof logs[0] === 'string') {
      return STRING_ARRAY;
  }
  return INVALID;
}

function addTagsToJsonLog(record, context) {
  metadata = extractResourceId(record)
  record['ddsource'] = metadata.source || DD_SOURCE;
  record['ddsourcecategory'] = DD_SOURCE_CATEGORY;
  record['service'] = DD_SERVICE;
  record['ddtags'] = metadata.tags.concat([DD_TAGS, 'forwardername:' + context.executionContext.functionName]).filter(Boolean).join(',');
  return record;
}

function addTagsToStringLog(stringLog, context) {
  jsonLog = {'message': stringLog};
  return addTagsToJsonLog(jsonLog, context);
}

function extractResourceId(record) {
  metadata = {'tags': [], 'source': ''};
  if (record.resourceId === undefined ||
      typeof record.resourceId !== 'string' ||
      !record.resourceId.toLowerCase().startsWith('/subscriptions/')) {
      return metadata;
  }
  var resourceId = record.resourceId.toLowerCase().split('/');
  if (resourceId.length > 2) {
      metadata.tags.push('subscription_id:' + resourceId[2]);
  }
  if (resourceId.length > 4) {
      metadata.tags.push('resource_group:' + resourceId[4]);
  }
  if (resourceId.length > 6) {
      metadata.source = resourceId[6].replace('microsoft.', 'azure.');
  }
  return metadata;
}

module.exports.forTests = {
    getLogFormat,
    extractResourceId,
};
