// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2020 Datadog, Inc.

var https = require('https');

const VERSION = '0.2.1';

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
const DD_URL = process.env.DD_URL || 'http-intake.logs.' + DD_SITE;
const DD_PORT = process.env.DD_PORT || 443;
const DD_TAGS = process.env.DD_TAGS || ''; // Replace '' by your comma-separated list of tags
const DD_SERVICE = process.env.DD_SERVICE || 'azure';
const DD_SOURCE = process.env.DD_SOURCE || 'azure';
const DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';

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

class ScrubberRule {
    constructor(name, pattern, replacement) {
        this.name = name;
        this.replacement = replacement;
        this.regexp = RegExp(pattern, 'g');
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
        this.options = {
            hostname: DD_URL,
            port: 443,
            path: '/v1/input',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'DD-API-KEY': DD_API_KEY
            },
            timeout: 2000
        };
        this.scrubber = new Scrubber(this.context, SCRUBBER_RULE_CONFIGS);
    }

    formatLogAndSend(messageType, record) {
        if (messageType == JSON_TYPE) {
            record = this.addTagsToJsonLog(record);
        } else {
            record = this.addTagsToStringLog(record);
        }
        return this.sendWithRetry(record);
    }

    sendWithRetry(record) {
        return new Promise((resolve, reject) => {
            return this.send(record)
                .then(res => {
                    resolve();
                })
                .catch(err => {
                    setTimeout(() => {
                        this.send(record)
                            .then(resolve)
                            .catch(err => {
                                this.context.log.error(
                                    `unable to send request after 2 tries, err: ${err}`
                                );
                                reject();
                            });
                    }, 1000);
                });
        });
    }

    send(record) {
        return new Promise((resolve, reject) => {
            const req = https
                .request(this.options, resp => {
                    if (resp.statusCode < 200 || resp.statusCode > 299) {
                        reject(`invalid status code ${resp.statusCode}`);
                    } else {
                        resolve();
                    }
                })
                .on('error', error => {
                    reject(error);
                });
            req.write(this.scrubber.scrub(JSON.stringify(record)));
            req.end();
        });
    }

    handleLogs(logs) {
        var promises = [];
        var logsType = this.getLogFormat(logs);
        switch (logsType) {
            case STRING:
                promises.push(this.formatLogAndSend(STRING_TYPE, logs));
                break;
            case JSON_STRING:
                logs = JSON.parse(logs);
                promises.push(this.formatLogAndSend(JSON_TYPE, logs));
                break;
            case JSON_OBJECT:
                promises.push(this.formatLogAndSend(JSON_TYPE, logs));
                break;
            case STRING_ARRAY:
                logs.forEach(log =>
                    promises.push(this.formatLogAndSend(STRING_TYPE, log))
                );
                break;
            case JSON_ARRAY:
                promises = this.handleJSONArrayLogs(logs, JSON_ARRAY);
                break;
            case BUFFER_ARRAY:
                this.handleJSONArrayLogs(logs, BUFFER_ARRAY);
                break;
            case JSON_STRING_ARRAY:
                promises = this.handleJSONArrayLogs(logs, JSON_STRING_ARRAY);
                break;
            case INVALID:
            default:
                this.context.log.warn('logs format is invalid');
                break;
        }
        return promises;
    }

    handleJSONArrayLogs(logs, logsType) {
        var promises = [];
        logs.forEach(message => {
            if (logsType == JSON_STRING_ARRAY) {
                try {
                    message = JSON.parse(message);
                } catch (err) {
                    this.context.log.warn(
                        'log is malformed json, sending as string'
                    );
                    promises.push(this.formatLogAndSend(STRING_TYPE, message));
                    return;
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
                    promises.push(
                        this.formatLogAndSend(STRING_TYPE, message.toString())
                    );
                    return;
                }
            }
            if (message.records != undefined) {
                message.records.forEach(message =>
                    promises.push(this.formatLogAndSend(JSON_TYPE, message))
                );
            } else {
                this.formatLogAndSend(JSON_TYPE, message);
            }
        });
        return promises;
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
    var promises = new EventhubLogForwarder(context).handleLogs(
        eventHubMessages
    );

    return Promise.all(promises.map(p => p.catch(e => e)));
};

module.exports.forTests = {
    EventhubLogForwarder,
    Scrubber,
    ScrubberRule,
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
