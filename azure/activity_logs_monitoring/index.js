// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2021 Datadog, Inc.

var https = require('https');

const VERSION = '0.5.7';

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
const DD_HTTP_URL = process.env.DD_URL || 'http-intake.logs.' + DD_SITE;
const DD_HTTP_PORT = process.env.DD_PORT || 443;
const DD_REQUEST_TIMEOUT_MS = 10000;
const DD_TAGS = process.env.DD_TAGS || ''; // Replace '' by your comma-separated list of tags
const DD_SERVICE = process.env.DD_SERVICE || 'azure';
const DD_SOURCE = process.env.DD_SOURCE || 'azure';
const DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';

const MAX_RETRIES = 4; // max number of times to retry a single http request
const RETRY_INTERVAL = 250; // amount of time (milliseconds) to wait before retrying request, doubles after every retry

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
    paths: [list of [list of fields in the log payload to iterate through to find the one to split]],
    keep_original_log: bool, if you'd like to preserve the original log in addition to the split ones or not,
    preserve_fields: bool, whether or not to keep the original log fields in the new split logs
}
You can also set the DD_LOG_SPLITTING_CONFIG env var with a JSON string in this format.
*/
const DD_LOG_SPLITTING_CONFIG = {
    // 'azure.datafactory': {
    //     paths: [['properties', 'Output', 'value']],
    //     keep_original_log: true,
    //     preserve_fields: true
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
    constructor(context, maxItemSizeBytes, maxBatchSizeBytes, maxItemsCount) {
        this.maxItemSizeBytes = maxItemSizeBytes;
        this.maxBatchSizeBytes = maxBatchSizeBytes;
        this.maxItemsCount = maxItemsCount;
    }

    batch(items) {
        var batches = [];
        var batch = [];
        var sizeBytes = 0;
        var sizeCount = 0;
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var itemSizeBytes = this.getSizeInBytes(item);
            if (
                sizeCount > 0 &&
                (sizeCount >= this.maxItemsCount ||
                    sizeBytes + itemSizeBytes > this.maxBatchSizeBytes)
            ) {
                batches.push(batch);
                batch = [];
                sizeBytes = 0;
                sizeCount = 0;
            }
            // all items exceeding maxItemSizeBytes are dropped here
            if (itemSizeBytes <= this.maxItemSizeBytes) {
                batch.push(item);
                sizeBytes += itemSizeBytes;
                sizeCount += 1;
            }
        }

        if (sizeCount > 0) {
            batches.push(batch);
        }
        return batches;
    }

    getSizeInBytes(string) {
        if (typeof string !== 'string') {
            string = JSON.stringify(string);
        }
        return Buffer.byteLength(string, 'utf8');
    }
}

class HTTPClient {
    constructor(context) {
        this.context = context;
        this.httpOptions = {
            hostname: DD_HTTP_URL,
            port: DD_HTTP_PORT,
            path: '/api/v2/logs',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'DD-API-KEY': DD_API_KEY,
                'DD-EVP-ORIGIN': 'azure'
            },
            timeout: DD_REQUEST_TIMEOUT_MS
        };
        this.scrubber = new Scrubber(this.context, SCRUBBER_RULE_CONFIGS);
        this.batcher = new Batcher(
            this.context,
            256 * 1000,
            4 * 1000 * 1000,
            400
        );
    }

    async sendAll(records) {
        var batches = this.batcher.batch(records);
        var promises = [];
        for (var i = 0; i < batches.length; i++) {
            promises.push(this.send(batches[i]));
        }
        return await Promise.all(
            promises.map(p => p.catch(e => this.context.log.error(e)))
        );
    }

    isStatusCodeValid(statusCode) {
        return statusCode >= 200 && statusCode <= 299;
    }

    shouldStatusCodeRetry(statusCode) {
        // don't retry 4xx responses
        return (
            !this.isStatusCodeValid(statusCode) &&
            (statusCode < 400 || statusCode > 499)
        );
    }

    send(record) {
        var numRetries = MAX_RETRIES;
        var retryInterval = RETRY_INTERVAL;
        return new Promise((resolve, reject) => {
            const sendRequest = (options, record) => {
                const retryRequest = errMsg => {
                    if (numRetries === 0) {
                        return reject(errMsg);
                    }
                    this.context.log.warn(
                        `Unable to send request, with error: ${errMsg}. Retrying ${numRetries} more times`
                    );
                    numRetries--;
                    retryInterval *= 2;
                    setTimeout(() => {
                        sendRequest(options, record);
                    }, retryInterval);
                };
                const req = https
                    .request(options, resp => {
                        if (this.isStatusCodeValid(resp.statusCode)) {
                            resolve(true);
                        } else if (
                            this.shouldStatusCodeRetry(resp.statusCode)
                        ) {
                            retryRequest(
                                `invalid status code ${resp.statusCode}`
                            );
                        } else {
                            reject(`invalid status code ${resp.statusCode}`);
                        }
                    })
                    .on('error', error => {
                        retryRequest(error.message);
                    })
                    .on('timeout', () => {
                        req.destroy();
                        retryRequest(
                            `request timed out after ${DD_REQUEST_TIMEOUT_MS}ms`
                        );
                    });
                req.write(this.scrubber.scrub(JSON.stringify(record)));
                req.end();
            };
            sendRequest(this.httpOptions, record);
        });
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
                    `Regexp for rule ${name} pattern ${settings['pattern']} is malformed, skipping. Please update the pattern for this rule to be applied.`
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

class EventhubLogHandler {
    constructor(context) {
        this.context = context;
        this.logSplittingConfig = getLogSplittingConfig();
        this.records = [];
    }

    findSplitRecords(record, fields) {
        var tempRecord = record;
        for (var i = 0; i < fields.length; i++) {
            // loop through the fields to find the one we want to split
            var fieldName = fields[i];
            if (
                tempRecord[fieldName] === undefined ||
                tempRecord[fieldName] === null
            ) {
                // if the field is null or undefined, return
                return null;
            } else {
                // there is some value for the field
                try {
                    // if for some reason we can't index into it, return null
                    tempRecord = tempRecord[fieldName];
                } catch {
                    return null;
                }
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
                var splitFieldFound = false;

                for (var i = 0; i < config.paths.length; i++) {
                    var fields = config.paths[i];
                    var recordsToSplit = this.findSplitRecords(record, fields);
                    if (
                        recordsToSplit === null ||
                        !(recordsToSplit instanceof Array)
                    ) {
                        // if we were unable find the field or if the field isn't an array, skip it
                        continue;
                    }
                    splitFieldFound = true;

                    for (var j = 0; j < recordsToSplit.length; j++) {
                        var splitRecord = recordsToSplit[j];
                        if (typeof splitRecord === 'string') {
                            try {
                                splitRecord = JSON.parse(splitRecord);
                            } catch (err) {}
                        }
                        var formattedSplitRecord = {};
                        var temp = formattedSplitRecord;
                        // re-create the same nested attributes with only the split log
                        for (var k = 0; k < fields.length; k++) {
                            if (k === fields.length - 1) {
                                // if it is the last field, add the split record
                                temp[fields[k]] = splitRecord;
                            } else {
                                temp[fields[k]] = {};
                                temp = temp[fields[k]];
                            }
                        }
                        formattedSplitRecord = {
                            parsed_arrays: formattedSplitRecord
                        };

                        if (config.preserve_fields) {
                            var newRecord = { ...originalRecord };
                        } else {
                            var newRecord = {
                                ddsource: source,
                                ddsourcecategory:
                                    originalRecord['ddsourcecategory'],
                                service: originalRecord['service'],
                                ddtags: originalRecord['ddtags']
                            };
                            if (originalRecord['time'] !== undefined) {
                                newRecord['time'] = originalRecord['time'];
                            }
                        }
                        Object.assign(newRecord, formattedSplitRecord);
                        this.records.push(newRecord);
                    }
                }
                if (config.keep_original_log || splitFieldFound !== true) {
                    // keep the original log if it is set in the config
                    // if it is false in the config, we should still write the log when we don't split
                    this.records.push(originalRecord);
                }
            } else {
                this.records.push(originalRecord);
            }
        } else {
            record = this.addTagsToStringLog(record);
            this.records.push(record);
        }
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

module.exports = async function(context, eventHubMessages) {
    if (!DD_API_KEY || DD_API_KEY === '<DATADOG_API_KEY>') {
        context.log.error(
            'You must configure your API key before starting this function (see ## Parameters section)'
        );
        return;
    }
    try {
        var handler = new EventhubLogHandler(context);
        var parsedLogs = handler.handleLogs(eventHubMessages);
    } catch (err) {
        context.log.error('Error raised when parsing logs: ', err);
        throw err;
    }
    var results = await new HTTPClient(context).sendAll(parsedLogs);

    if (results.every(v => v === true) !== true) {
        context.log.error(
            'Some messages were unable to be sent. See other logs for details.'
        );
    }
};

module.exports.forTests = {
    EventhubLogHandler,
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
