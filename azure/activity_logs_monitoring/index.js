// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2019 Datadog, Inc.

var tls = require('tls');

const VERSION = '0.1.1';

const STRING = 'string'; // example: 'some message'
const STRING_ARRAY = 'string-array'; // example: ['one message', 'two message', ...]
const JSON_OBJECT = 'json-object'; // example: {"key": "value"}
const JSON_ARRAY = 'json-array'; // example: [{"key": "value"}, {"key": "value"}, ...] or [{"records": [{}, {}, ...]}, {"records": [{}, {}, ...]}, ...]
const JSON_STRING = 'json-string'; // example: '{"key": "value"}'
const JSON_STRING_ARRAY = 'json-string-array'; // example: ['{"records": [{}, {}]}'] or ['{"key": "value"}']
const INVALID = 'invalid';

const DD_API_KEY = process.env.DD_API_KEY || '<DATADOG_API_KEY>';
const DD_SITE = process.env.DD_SITE || 'datadoghq.com';
const DD_URL = process.env.DD_URL || 'functions-intake.logs.' + DD_SITE;
const DD_PORT = process.env.DD_PORT || DD_SITE === 'datadoghq.eu' ? 443 : 10516;
const DD_TAGS = process.env.DD_TAGS || ''; // Replace '' by your comma-separated list of tags
const DD_SERVICE = process.env.DD_SERVICE || 'azure';
const DD_SOURCE = process.env.DD_SOURCE || 'azure';
const DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';

module.exports = function(context, eventHubMessages) {
    if (!DD_API_KEY || DD_API_KEY === '<DATADOG_API_KEY>') {
        context.log.error(
            'You must configure your API key before starting this function (see ## Parameters section)'
        );
        return;
    }

    var socket = getSocket(context);
    var sender = tagger => record => {
        record = tagger(record, context);
        if (!send(socket, record)) {
            // Retry once
            socket = getSocket(context);
            send(socket, record);
        }
    };

    handleLogs(sender, eventHubMessages, context);

    socket.end();
    context.done();
};

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

function handleLogs(sender, logs, context) {
    var logsType = getLogFormat(logs);
    switch (logsType) {
        case STRING:
            sender(addTagsToStringLog)(logs);
            break;
        case JSON_STRING:
            logs = JSON.parse(logs);
            sender(addTagsToJsonLog)(logs);
            break;
        case JSON_OBJECT:
            sender(addTagsToJsonLog)(logs);
            break;
        case STRING_ARRAY:
            logs.forEach(sender(addTagsToStringLog));
            break;
        case JSON_ARRAY:
            handleJSONArrayLogs(sender, logs, JSON_ARRAY);
            break;
        case JSON_STRING_ARRAY:
            handleJSONArrayLogs(sender, logs, JSON_STRING_ARRAY);
            break;
        case INVALID:
        default:
            context.log.warn('logs format is invalid');
            break;
    }
}

function handleJSONArrayLogs(sender, logs, logsType) {
    logs.forEach(message => {
        if (logsType == JSON_STRING_ARRAY) {
            try {
                message = JSON.parse(message);
            } catch (err) {
                context.log.warn('log is malformed json, sending as string');
                sender(addTagsToStringLog)(message);
                return;
            }
        }
        if (message.records != undefined) {
            message.records.forEach(sender(addTagsToJsonLog));
        } else {
            sender(addTagsToJsonLog)(message);
        }
    });
}

function getLogFormat(logs) {
    if (typeof logs === 'string') {
        if (isJsonString(logs)) {
            return JSON_STRING;
        }
        return STRING;
    }
    if (!Array.isArray(logs) && typeof logs === 'object' && logs !== null) {
        return JSON_OBJECT;
    }
    if (!Array.isArray(logs)) {
        return INVALID;
    }
    if (typeof logs[0] === 'object') {
        return JSON_ARRAY;
    }
    if (typeof logs[0] === 'string') {
        if (isJsonString(logs[0])) {
            return JSON_STRING_ARRAY;
        } else {
            return STRING_ARRAY;
        }
    }
    return INVALID;
}

function isJsonString(record) {
    try {
        JSON.parse(record);
        return true;
    } catch (err) {
        return false;
    }
}

function addTagsToJsonLog(record, context) {
    metadata = extractResourceId(record);
    record['ddsource'] = metadata.source || DD_SOURCE;
    record['ddsourcecategory'] = DD_SOURCE_CATEGORY;
    record['service'] = DD_SERVICE;
    record['ddtags'] = metadata.tags
        .concat([
            DD_TAGS,
            'forwardername:' + context.executionContext.functionName
        ])
        .filter(Boolean)
        .join(',');
    return record;
}

function addTagsToStringLog(stringLog, context) {
    jsonLog = { message: stringLog };
    return addTagsToJsonLog(jsonLog, context);
}

function extractResourceId(record) {
    metadata = { tags: [], source: '' };
    if (
        record.resourceId === undefined ||
        typeof record.resourceId !== 'string'
    ) {
        return metadata;
    } else if (record.resourceId.toLowerCase().startsWith('/subscriptions/')) {
        var resourceId = record.resourceId.toLowerCase().split('/');
        if (resourceId.length > 2) {
            metadata.tags.push('subscription_id:' + resourceId[2]);
        }
        if (resourceId.length > 4) {
            metadata.tags.push('resource_group:' + resourceId[4]);
        }
        if (resourceId.length > 6 && resourceId[6]) {
            metadata.source = resourceId[6].replace('microsoft.', 'azure.');
        }
        return metadata;
    } else if (record.resourceId.toLowerCase().startsWith('/tenants/')) {
        var resourceId = record.resourceId.toLowerCase().split('/');
        if (resourceId.length > 4 && resourceId[4]) {
            metadata.tags.push('tenant:' + resourceId[2]);
            metadata.source = resourceId[4]
                .replace('microsoft.', 'azure.')
                .replace('aadiam', 'activedirectory');
        }
        return metadata;
    } else {
        return metadata;
    }
}

module.exports.forTests = {
    getLogFormat,
    extractResourceId,
    handleLogs,
    isJsonString,
    addTagsToStringLog,
    addTagsToJsonLog,
    constants: {
        STRING,
        STRING_ARRAY,
        JSON_OBJECT,
        JSON_ARRAY,
        JSON_STRING,
        JSON_STRING_ARRAY,
        INVALID
    }
};
