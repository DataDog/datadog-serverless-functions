// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2021 Datadog, Inc.

var https = require('https');
var tls = require('tls');

const VERSION = '0.4.0';

const STRING = 'string'; // example: 'some message'
const STRING_ARRAY = 'string-array'; // example: ['one message', 'two message', ...]
const JSON_OBJECT = 'json-object'; // example: {"key": "value"}
const JSON_ARRAY = 'json-array'; // example: [{"key": "value"}, {"key": "value"}, ...] or [{"records": [{}, {}, ...]}, {"records": [{}, {}, ...]}, ...]
const BUFFER_ARRAY = 'buffer-array'; // example: [<Buffer obj>, <Buffer obj>]
const JSON_STRING = 'json-string'; // example: '{"key": "value"}'
const JSON_STRING_ARRAY = 'json-string-array'; // example: ['{"records": [{}, {}]}'] or ['{"key": "value"}']
const INVALID = 'invalid';

const JSON_TYPE = 'json';
const STRING_TYPE = 'string';

const DD_API_KEY = process.env.DD_API_KEY || '<DATADOG_API_KEY>';
const DD_SITE = process.env.DD_SITE || 'datadoghq.com';
const DD_HTTP_URL = process.env.DD_HTTP_URL || 'http-intake.logs.' + DD_SITE;
const DD_HTTP_PORT = process.env.DD_HTTP_PORT || 443;
const DD_TCP_URL = process.env.DD_TCP_URL || 'functions-intake.logs.' + DD_SITE;
const DD_TCP_PORT = DD_SITE === 'datadoghq.eu' ? 443 : 10516;
const DD_TAGS = process.env.DD_TAGS || ''; // Replace '' by your comma-separated list of tags
const DD_SERVICE = process.env.DD_SERVICE || 'azure';
const DD_SOURCE = process.env.DD_SOURCE || 'azure';
const DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';
const USE_TCP = process.env.DD_USE_TCP || false;

/*
To scrub PII from your logs, uncomment the applicable configs below. If you'd like to scrub more than just
emails and IP addresses, add your own config to this map in the format
NAME: {pattern: <regex_pattern>, replacement: <string to replace matching text with>}
*/
const SCRUBBER_RULE_CONFIGS = {
    // REDACT_IP: {
    //     pattern: /[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/,
    //     replacement: 'xxx.xxx.xxx.xxx'
    // },
    // REDACT_EMAIL: {
    //     pattern: /[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/,
    //     replacement: 'xxxxx@xxxxx.com'
    // }
};

/*
To split array-type fields in your logs into individual logs, you can add sections to the map below. An example of
a potential use case with azure.datafactory is there to show the format:
{
  source_type:
    path: [list of fields in the log payload to iterate through to find the one to split],
    keep_original_log: bool, if you'd like to preserve the original log in addition to the split ones or not
}
You can also set the DD_LOG_SPLITTING_CONFIG env var with a JSON string in this format.
*/
const DD_LOG_SPLITTING_CONFIG = {
    // 'azure.datafactory': {
    //     path: ['properties', 'Output', 'value'],
    //     keep_original_log: true
    // }
};

function getLogSplittingConfig() {
    try {
        return JSON.parse(process.env.DD_LOG_SPLITTING_CONFIG);
    } catch {
        return DD_LOG_SPLITTING_CONFIG;
    }
}

class ScrubberRule {
    constructor(name, pattern, replacement) {
        this.name = name;
        this.replacement = replacement;
        this.regexp = RegExp(pattern, 'g');
    }
}

class Batcher {
    constructor(
        context,
        max_item_size_bytes,
        max_batch_size_bytes,
        max_items_count
    ) {
        this.max_item_size_bytes = max_item_size_bytes;
        this.max_batch_size_bytes = max_batch_size_bytes;
        this.max_items_count = max_items_count;
    }

    batch(items) {
        var batches = [];
        var batch = [];
        var size_bytes = 0;
        var size_count = 0;
        items.forEach(item => {
            var item_size_bytes = this.getSizeInBytes(item);
            if (
                size_count > 0 &&
                (size_count >= this.max_items_count ||
                    size_bytes + item_size_bytes > this.max_batch_size_bytes)
            ) {
                batches.push(batch);
                batch = [];
                size_bytes = 0;
                size_count = 0;
            }
            // all items exceeding max_item_size_bytes are dropped here
            if (item_size_bytes <= this.max_item_size_bytes) {
                batch.push(item);
                size_bytes += item_size_bytes;
                size_count += 1;
            }
        });

        if (size_count > 0) {
            batches.push(batch);
        }
        return batches;
    }

    getSizeInBytes(string) {
        if (typeof string !== 'string') {
            string = JSON.stringify(string);
        }
        return string.length;
    }
}

class Scrubber {
    constructor(context, configs) {
        var rules = [];
        for (const [name, settings] of Object.entries(configs)) {
            try {
                rules.push(
                    new ScrubberRule(
                        name,
                        settings['pattern'],
                        settings['replacement']
                    )
                );
            } catch {
                context.log.error(
                    `Regexp for rule ${name} pattern ${
                        settings['pattern']
                    } is malformed, skipping. Please update the pattern for this rule to be applied.`
                );
            }
        }
        this.rules = rules;
    }

    scrub(record) {
        if (!this.rules) {
            return record;
        }
        this.rules.forEach(rule => {
            record = record.replace(rule.regexp, rule.replacement);
        });
        return record;
    }
}

class EventhubLogForwarder {
    constructor(context) {
        this.context = context;
        this.http_options = {
            hostname: DD_HTTP_URL,
            port: DD_HTTP_PORT,
            path: '/v1/input',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'DD-API-KEY': DD_API_KEY
            },
        };
        this.scrubber = new Scrubber(this.context, SCRUBBER_RULE_CONFIGS);
        this.logSplittingConfig = getLogSplittingConfig();
        this.records = [];
    }

    findSplitRecords(record, fields) {
        var tempRecord = record;
        for (var i = 0; i < fields.length; i++) {
            // loop through the fields to find the one we want to split
            var fieldName = fields[i];
            if (tempRecord[fieldName] !== undefined) {
                tempRecord = tempRecord[fieldName];
            } else {
                this.context.log.error(
                    'unable to split log based on log config, falling back to sending existing log.'
                );
                this.records.push(record);
                return null;
            }
        }
        return tempRecord;
    }

    formatLog(messageType, record) {
        if (messageType == JSON_TYPE) {
            var originalRecord = this.addTagsToJsonLog(record);
            var source = originalRecord['ddsource'];
            var config = this.logSplittingConfig[source];
            if (config !== undefined) {
                var fields = config.path;

                if (config.keep_original_log) {
                    this.records.push(originalRecord);
                }

                var recordsToSplit = this.findSplitRecords(record, fields);
                if (recordsToSplit === null) {
                    return;
                }

                for (var j = 0; j < recordsToSplit.length; j++) {
                    var splitRecord = recordsToSplit[j];
                    if (typeof splitRecord === 'string') {
                        try {
                            splitRecord = JSON.parse(splitRecord);
                        } catch (err) {
                            splitRecord = { message: splitRecord };
                        }
                    }
                    var newRecord = {
                        ddsource: source,
                        ddsourcecategory: originalRecord['ddsourcecategory'],
                        service: originalRecord['service'],
                        tags: originalRecord['tags']
                    };
                    Object.assign(newRecord, splitRecord);
                    this.records.push(newRecord);
                }
            } else {
                this.records.push(originalRecord);
            }
        } else {
            record = this.addTagsToStringLog(record);
            this.records.push(record);
        }
    }

    sendWithRetry(record) {
        return new Promise((resolve, reject) => {
            return this.send(record)
                .then(res => {
                    resolve(true);
                })
                .catch(err => {
                    this.send(record)
                        .then(res => {
                            resolve(true);
                        })
                        .catch(err => {
                            reject(
                                `unable to send request after 2 tries, err: ${err}`
                            );
                        });
                });
        });
    }

    send(record) {
        return new Promise((resolve, reject) => {
            const req = https
                .request(this.http_options, resp => {
                    if (resp.statusCode < 200 || resp.statusCode > 299) {
                        reject(`invalid status code ${resp.statusCode}`);
                    } else {
                        resolve(true);
                    }
                })
                .on('error', error => {
                    reject(error);
                });
            req.write(this.scrubber.scrub(JSON.stringify(record)));
            req.end();
        });
    }

    createBatches(logs) {
        var parsedLogs = this.handleLogs(logs);
        if (USE_TCP) {
            return new Batcher(this.context, 256 * 1000, 256 * 1000, 1).batch(
                parsedLogs
            );
        }
        return new Batcher(
            this.context,
            256 * 1000,
            4 * 1000 * 1000,
            400
        ).batch(parsedLogs);
    }

    handleLogs(logs) {
        var logsType = this.getLogFormat(logs);
        switch (logsType) {
            case STRING:
                this.formatLog(STRING_TYPE, logs);
                break;
            case JSON_STRING:
                logs = JSON.parse(logs);
                this.formatLog(JSON_TYPE, logs);
                break;
            case JSON_OBJECT:
                this.formatLog(JSON_TYPE, logs);
                break;
            case STRING_ARRAY:
                logs.forEach(log => this.formatLog(STRING_TYPE, log));
                break;
            case JSON_ARRAY:
                this.handleJSONArrayLogs(logs, JSON_ARRAY);
                break;
            case BUFFER_ARRAY:
                this.handleJSONArrayLogs(logs, BUFFER_ARRAY);
                break;
            case JSON_STRING_ARRAY:
                this.handleJSONArrayLogs(logs, JSON_STRING_ARRAY);
                break;
            case INVALID:
                this.context.log.error('Log format is invalid: ', logs);
                break;
            default:
                this.context.log.error('Log format is invalid: ', logs);
                break;
        }
        return this.records;
    }

    handleJSONArrayLogs(logs, logsType) {
        for (var i = 0; i < logs.length; i++) {
            var message = logs[i];
            if (logsType == JSON_STRING_ARRAY) {
                try {
                    message = JSON.parse(message);
                } catch (err) {
                    this.context.log.warn(
                        'log is malformed json, sending as string'
                    );
                    this.formatLog(STRING_TYPE, message);
                    continue;
                }
            }
            // If the message is a buffer object, the data type has been set to binary.
            if (logsType == BUFFER_ARRAY) {
                try {
                    message = JSON.parse(message.toString());
                } catch (err) {
                    this.context.log.warn(
                        'log is malformed json, sending as string'
                    );
                    this.formatLog(STRING_TYPE, message.toString());
                    continue;
                }
            }
            if (message.records != undefined) {
                message.records.forEach(message =>
                    this.formatLog(JSON_TYPE, message)
                );
            } else {
                this.formatLog(JSON_TYPE, message);
            }
        }
    }

    getLogFormat(logs) {
        if (typeof logs === 'string') {
            if (this.isJsonString(logs)) {
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
        if (Buffer.isBuffer(logs[0])) {
            return BUFFER_ARRAY;
        }
        if (typeof logs[0] === 'object') {
            return JSON_ARRAY;
        }
        if (typeof logs[0] === 'string') {
            if (this.isJsonString(logs[0])) {
                return JSON_STRING_ARRAY;
            } else {
                return STRING_ARRAY;
            }
        }
        return INVALID;
    }

    isJsonString(record) {
        try {
            JSON.parse(record);
            return true;
        } catch (err) {
            return false;
        }
    }

    addTagsToJsonLog(record) {
        var metadata = this.extractMetadataFromResource(record);
        record['ddsource'] = metadata.source || DD_SOURCE;
        record['ddsourcecategory'] = DD_SOURCE_CATEGORY;
        record['service'] = DD_SERVICE;
        record['ddtags'] = metadata.tags
            .concat([
                DD_TAGS,
                'forwardername:' + this.context.executionContext.functionName
            ])
            .filter(Boolean)
            .join(',');
        return record;
    }

    addTagsToStringLog(stringLog) {
        var jsonLog = { message: stringLog };
        return this.addTagsToJsonLog(jsonLog);
    }

    createResourceIdArray(record) {
        // Convert the resource ID in the record to an array, handling beginning/ending slashes
        var resourceId = record.resourceId.toLowerCase().split('/');
        if (resourceId[0] === '') {
            resourceId = resourceId.slice(1);
        }
        if (resourceId[resourceId.length - 1] === '') {
            resourceId.pop();
        }
        return resourceId;
    }

    isSource(resourceIdPart) {
        // Determine if a section of a resource ID counts as a "source," in our case it means it starts with 'microsoft.'
        return resourceIdPart.startsWith('microsoft.');
    }

    formatSourceType(sourceType) {
        return sourceType.replace('microsoft.', 'azure.');
    }

    extractMetadataFromResource(record) {
        var metadata = { tags: [], source: '' };
        if (
            record.resourceId === undefined ||
            typeof record.resourceId !== 'string'
        ) {
            return metadata;
        }

        var resourceId = this.createResourceIdArray(record);

        if (resourceId[0] === 'subscriptions') {
            if (resourceId.length > 1) {
                metadata.tags.push('subscription_id:' + resourceId[1]);
                if (resourceId.length == 2) {
                    metadata.source = 'azure.subscription';
                    return metadata;
                }
            }
            if (resourceId.length > 3) {
                if (
                    resourceId[2] === 'providers' &&
                    this.isSource(resourceId[3])
                ) {
                    // handle provider-only resource IDs
                    metadata.source = this.formatSourceType(resourceId[3]);
                } else {
                    metadata.tags.push('resource_group:' + resourceId[3]);
                    if (resourceId.length == 4) {
                        metadata.source = 'azure.resourcegroup';
                        return metadata;
                    }
                }
            }
            if (resourceId.length > 5 && this.isSource(resourceId[5])) {
                metadata.source = this.formatSourceType(resourceId[5]);
            }
        } else if (resourceId[0] === 'tenants') {
            if (resourceId.length > 3 && resourceId[3]) {
                metadata.tags.push('tenant:' + resourceId[1]);
                metadata.source = this.formatSourceType(resourceId[3]).replace(
                    'aadiam',
                    'activedirectory'
                );
            }
        }
        return metadata;
    }
}

function getSocket(context) {
    var socket = tls.connect({ port: DD_TCP_PORT, host: DD_TCP_URL });
    socket.on('error', err => {
        context.log.error(err.toString());
        socket.end();
    });

    return socket;
}
function sendTCP(socket, record) {
    record = record[0];
    return socket.write(DD_API_KEY + ' ' + JSON.stringify(record) + '\n');
}

module.exports = async function(context, eventHubMessages) {
    if (!DD_API_KEY || DD_API_KEY === '<DATADOG_API_KEY>') {
        context.log.error(
            'You must configure your API key before starting this function (see ## Parameters section)'
        );
        return;
    }
    try {
        var forwarder = new EventhubLogForwarder(context);
        var batches = forwarder.createBatches(eventHubMessages);
    } catch (err) {
        context.log.error('Error raised when creating batches', err);
        throw err;
    }
    if (USE_TCP) {
        var socket = getSocket(context);
        for (i = 0; i < batches.length; i++) {
            if (!sendTCP(socket, batches[i])) {
                // Retry once
                socket = getSocket(context);
                sendTCP(socket, batches[i]);
            }
        }
        socket.end();
    } else {
        var promises = [];
        for (i = 0; i < batches.length; i++) {
            promises.push(forwarder.sendWithRetry(batches[i]));
        }
        var results = await Promise.all(
            promises.map(p => p.catch(e => context.log.error(e)))
        );
        if (results.every(v => v === true) !== true) {
            context.log.error('some messages were unable to be sent.');
        }
    }
};

module.exports.forTests = {
    EventhubLogForwarder,
    Scrubber,
    ScrubberRule,
    Batcher,
    constants: {
        STRING,
        STRING_ARRAY,
        JSON_OBJECT,
        JSON_ARRAY,
        BUFFER_ARRAY,
        JSON_STRING,
        JSON_STRING_ARRAY,
        INVALID
    }
};
