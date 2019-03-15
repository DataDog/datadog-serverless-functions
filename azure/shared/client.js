// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2019 Datadog, Inc.

var tls = require('tls');

const VERSION = "0.1.0";

const STRING = 'string';  // example: 'some message'
const STRING_ARRAY = 'string-array';  // example: ['one message', 'two message', ...]
const JSON_OBJECT = 'json-object';  // example: {"key": "value"}
const JSON_RECORDS = 'json-records';  // example: [{"records": [{}, {}, ...]}, {"records": [{}, {}, ...]}, ...]
const JSON_ARRAY = 'json-array';  // example: [{"key": "value"}, {"key": "value"}, ...]
const INVALID = 'invalid';

var DD_API_KEY = process.env.DD_API_KEY || '<DATADOG_API_KEY>';
var DD_URL = process.env.DD_URL || 'functions-intake.logs.datadoghq.com';
var DD_TAGS = process.env.DD_TAGS || '<TAG_KEY>:<TAG_VALUE>';
var DD_PORT = process.env.DD_PORT || 10516;
var DD_SERVICE = process.env.DD_SERVICE || 'azure';
var DD_SOURCE = process.env.DD_SOURCE || 'azure';
var DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';

function getSocket(context) {
    var socket = tls.connect({ port: DD_PORT, host: DD_URL });
    socket.on('error', err => {
        context.log.error(err.toString());
        socket.end();
    });

    return socket;
}

function send(socket, record) {
    return socket.write(DD_API_KEY + ' ' + JSON.stringify(record) + '\n');
}


function handleLogs(handler, logs, context) {
    var logsType = getLogFormat(logs);
    switch (logsType) {
        case STRING:
            handler(addTagsToStringLog)(logs);
            break;
        case JSON_OBJECT:
            handler(addTagsToJsonLog)(logs);
            break;
        case STRING_ARRAY:
            logs.forEach(handler(addTagsToStringLog));
            break;
        case JSON_RECORDS:
            logs.forEach(message => {
                message.records.forEach(handler(addTagsToJsonLog));
            });
            break;
        case JSON_ARRAY:
            logs.forEach(handler(addTagsToJsonLog));
            break;
        case INVALID:
        default:
            context.log.warn('logs format is invalid');
            break;
    }
}

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
    jsonLog = { 'message': stringLog };
    return addTagsToJsonLog(jsonLog, context);
}

function extractResourceId(record) {
    metadata = { 'tags': [], 'source': '' };
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

module.exports = {
    getSocket,
    send,
    handleLogs,
    DD_API_KEY,
    DD_TAGS,
    VERSION
};

module.exports.forTests = {
    getLogFormat,
    extractResourceId,
    constants: {
        STRING,
        STRING_ARRAY,
        JSON_OBJECT,
        JSON_RECORDS,
        JSON_ARRAY,
        INVALID
    }
};
