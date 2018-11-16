// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2018 Datadog, Inc.

var tls = require('tls');

const STRING = 'string';  // eventHubMessages = 'some message'
const STRING_ARRAY = 'string-array';  // eventHubMessages = ['one message', 'two message', ...]
const RAW_JSON = 'raw-json';  // eventHubMessages = {"key": "value"}
const DEFAULT_JSON = 'default-json';  // eventHubMessages = [{"records": [{}, {}, ...]}, {"records": [{}, {}, ...]}, ...]
const JSON_NO_RECORDS = 'json_no_records';  // eventHubMessages = [{"key": "value"}, {"key": "value"}, ...]
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
            handleLogs(addTagsStringLog)(eventHubMessages);
            break;
        case RAW_JSON:
            handleLogs(addTagsJsonLog)(eventHubMessages);
            break;
        case STRING_ARRAY:
            eventHubMessages.forEach( handleLogs(addTagsStringLog) );
            break;
        case DEFAULT_JSON:
            eventHubMessages.forEach( message => {
                message.records.forEach( handleLogs(addTagsJsonLog) );
            })
            break;
        case JSON_NO_RECORDS:
            eventHubMessages.forEach( handleLogs(addTagsJsonLog) );
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
        return RAW_JSON;
    }
    if (!Array.isArray(eventHubMessages)) {
        return INVALID;
    }
    if (typeof eventHubMessages[0] === 'object') {
        if (eventHubMessages[0].records !== undefined) {
            return DEFAULT_JSON;
        } else {
            return JSON_NO_RECORDS;
        }
    }
    if (typeof eventHubMessages[0] === 'string') {
        return STRING_ARRAY;
    }
    return INVALID;
}

function addTagsJsonLog(record, context) {
    record['ddsource'] = DD_SOURCE;
    record['ddsourcecategory'] = DD_SOURCE_CATEGORY;
    record['service'] = DD_SERVICE;
    record['ddtags'] = [DD_TAGS, 'forwardername:' + context.executionContext.functionName].filter(Boolean).join(',');
    return record;
}

function addTagsStringLog(stringLog, context) {
    jsonLog = {'message': stringLog};
    return addTagsJsonLog(jsonLog, context);
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
module.exports.getEventHubMessagesFormat = getEventHubMessagesFormat;
module.exports.STRING = STRING;
module.exports.STRING_ARRAY = STRING_ARRAY;
module.exports.RAW_JSON = RAW_JSON;
module.exports.DEFAULT_JSON = DEFAULT_JSON;
module.exports.JSON_NO_RECORDS = JSON_NO_RECORDS;
module.exports.INVALID = INVALID;
