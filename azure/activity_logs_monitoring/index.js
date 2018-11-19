// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2018 Datadog, Inc.

var tls = require('tls');

const STRING = 'string';  // eventHubMessages = 'some message'
const STRING_ARRAY = 'string-array';  // eventHubMessages = ['one message', 'two message', ...]
const JSON_OBJECT = 'json-object';  // eventHubMessages = {"key": "value"}
const JSON_RECORDS = 'json-records';  // eventHubMessages = [{"records": [{}, {}, ...]}, {"records": [{}, {}, ...]}, ...]
const JSON_ARRAY = 'json-array';  // eventHubMessages = [{"key": "value"}, {"key": "value"}, ...]
const INVALID = 'invalid';

var DD_API_KEY = process.env.DD_API_KEY || '<DATADOG_API_KEY>';
var DD_URL = process.env.DD_URL || 'lambda-intake.logs.datadoghq.com';
var DD_TAGS = process.env.DD_TAGS || '<TAG_KEY>:<TAG_VALUE>';
var DD_PORT = process.env.DD_PORT || 10516;
var DD_SERVICE = process.env.DD_SERVICE || 'azure';
var DD_SOURCE = process.env.DD_SOURCE || 'azure';
var DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';

module.exports = function (context, eventHubMessages) {
    if (DD_API_KEY === '<DATADOG_API_KEY>' || DD_API_KEY === '' || DD_API_KEY === undefined) {
        context.log('You must configure your API key before starting this function (see ## Parameters section)');
        return;
    }

    if (DD_TAGS === '<TAG_KEY>:<TAG_VALUE>') {
        context.log.warn('You must configure your tags with a comma separated list of tags or an empty string');
    }

    var eventHubType = getEventHubMessagesFormat(eventHubMessages);

    var socket = connectToDD(context);
    var handleLogs = tagger => record => {
        record = tagger(record, context);
        if (!send(socket, record)) {
            // Retry once
            socket = connectToDD(context);
            send(socket, record);
        }
    }

    switch (eventHubType) {
        case STRING:
            handleLogs(addTagsToStringLog)(eventHubMessages);
            break;
        case JSON_OBJECT:
            handleLogs(addTagsToJsonLog)(eventHubMessages);
            break;
        case STRING_ARRAY:
            eventHubMessages.forEach( handleLogs(addTagsToStringLog) );
            break;
        case JSON_RECORDS:
            eventHubMessages.forEach( message => {
                message.records.forEach( handleLogs(addTagsToJsonLog) );
            })
            break;
        case JSON_ARRAY:
            eventHubMessages.forEach( handleLogs(addTagsToJsonLog) );
            break;
        case INVALID:
        default:
            context.log.warn('eventHubMessages format is invalid');
            break;
    }

    socket.end();
    context.done();
};

function getEventHubMessagesFormat(eventHubMessages) {
    if (typeof eventHubMessages === 'string') {
        return STRING;
    }
    if (!Array.isArray(eventHubMessages) && typeof eventHubMessages === 'object' && eventHubMessages !== null) {
        return JSON_OBJECT;
    }
    if (!Array.isArray(eventHubMessages)) {
        return INVALID;
    }
    if (typeof eventHubMessages[0] === 'object') {
        if (eventHubMessages[0].records !== undefined) {
            return JSON_RECORDS;
        } else {
            return JSON_ARRAY;
        }
    }
    if (typeof eventHubMessages[0] === 'string') {
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

function connectToDD(context) {
    var socket = tls.connect({port: DD_PORT, host: DD_URL});
    socket.on('error', err => {
        context.log.error(err.toString());
        socket.end();
    });

    return socket;
}

function send(socket, record) {
    return socket.write(DD_API_KEY + ' ' + JSON.stringify(record) + '\n');
}

// For tests
module.exports.forTests = {
    getEventHubMessagesFormat,
    extractResourceId,
    STRING,
    STRING_ARRAY,
    JSON_OBJECT,
    JSON_RECORDS,
    JSON_ARRAY,
    INVALID,
}
