// Unless explicitly stated otherwise all files in this repository are licensed
// under the Apache License Version 2.0.
// This product includes software developed at Datadog (https://www.datadoghq.com/).
// Copyright 2025 Datadog, Inc.

const { app, InvocationContext } = require('@azure/functions');

const VERSION = '2.1.0';

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
const DD_SERVICE = process.env.DD_SERVICE || 'azure'; // Replace 'azure' with the name of your service
const DD_SOURCE = process.env.DD_SOURCE || 'azure';
const DD_SOURCE_CATEGORY = process.env.DD_SOURCE_CATEGORY || 'azure';
const DD_PARSE_DEFENDER_LOGS = process.env.DD_PARSE_DEFENDER_LOGS; // Boolean whether to enable special parsing of Defender for Cloud logs. Set to 'false' to disable

const MAX_RETRIES = 4; // max number of times to retry a single http request
const RETRY_INTERVAL = 250; // amount of time (milliseconds) to wait before retrying request, doubles after every retry

// constants relating to Defender for Cloud logs
const MSFT_DEFENDER_FOR_CLOUD = 'Microsoft Defender for Cloud';
const AZURE_SECURITY_CENTER = 'Azure Security Center';
const SECURITY_ASSESSMENTS = 'Microsoft.Security/assessments';
const SECURITY_SUB_ASSESSMENTS = 'Microsoft.Security/assessments/subAssessments';
const SECURITY_COMPLIANCE_ASSESSMENTS = 'Microsoft.Security/regulatoryComplianceStandards/regulatoryComplianceControls/regulatoryComplianceAssessments';
const SECURITY_SCORES = 'Microsoft.Security/secureScores';
const SECURITY_SCORE_CONTROLS = 'Microsoft.Security/secureScores/secureScoreControls';
const DEFENDER_FOR_CLOUD_PRODUCTS = [MSFT_DEFENDER_FOR_CLOUD, AZURE_SECURITY_CENTER];
const DEFENDER_FOR_CLOUD_RESOURCE_TYPES = [SECURITY_ASSESSMENTS, SECURITY_SUB_ASSESSMENTS, SECURITY_COMPLIANCE_ASSESSMENTS, SECURITY_SCORES, SECURITY_SCORE_CONTROLS];

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

function shouldParseDefenderForCloudLogs() {
    // Default to true if the env variable is not set, is null, etc
    if (typeof DD_PARSE_DEFENDER_LOGS !== 'string') {
        return true;
    }
    const parse_defender_logs = DD_PARSE_DEFENDER_LOGS.toLowerCase();
    return !(parse_defender_logs === 'false' || parse_defender_logs === 'f');
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

class ScrubberRule {
    /**
     * @param {string} name
     * @param {string} pattern
     * @param {string} replacement
     */
    constructor(name, pattern, replacement) {
        this.name = name;
        this.replacement = replacement;
        this.regexp = RegExp(pattern, 'g');
    }
}

class Batcher {
    /**
     * @param {number} maxItemSizeBytes
     * @param {number} maxBatchSizeBytes
     * @param {number} maxItemsCount
     */
    constructor(maxItemSizeBytes, maxBatchSizeBytes, maxItemsCount) {
        this.maxItemSizeBytes = maxItemSizeBytes;
        this.maxBatchSizeBytes = maxBatchSizeBytes;
        this.maxItemsCount = maxItemsCount;
    }

    batch(items) {
        let batches = [];
        let batch = [];
        let sizeBytes = 0;
        let sizeCount = 0;
        for (const item of items) {
            let itemSizeBytes = this.getSizeInBytes(item);
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
    /**
     * @param {InvocationContext} context
     */
    constructor(context) {
        this.context = context;
        this.url = `https://${DD_HTTP_URL}:${DD_HTTP_PORT}/api/v2/logs`;
        this.scrubber = new Scrubber(this.context, SCRUBBER_RULE_CONFIGS);
        this.batcher = new Batcher(256 * 1000, 4 * 1000 * 1000, 400);
    }

    async sendAll(records) {
        let batches = this.batcher.batch(records);
        return await Promise.all(
            batches.map(async batch => {
                try {
                    return await this.send(batch);
                } catch (e) {
                    this.context.error(e);
                }
            })
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

    async send(record, retries = MAX_RETRIES, retryInterval = RETRY_INTERVAL) {
        const retryRequest = async errMsg => {
            if (retries === 0) {
                throw new Error(errMsg);
            }
            this.context.warn(
                `Unable to send request, with error: ${errMsg}. Retrying ${retries} more times`
            );
            retries--;
            retryInterval *= 2;
            await sleep(retryInterval);
            return await this.send(record, retries, retryInterval);
        };
        try {
            const resp = await fetch(this.url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'DD-API-KEY': DD_API_KEY,
                    'DD-EVP-ORIGIN': 'azure'
                },
                signal: AbortSignal.timeout(DD_REQUEST_TIMEOUT_MS),
                body: this.scrubber.scrub(JSON.stringify(record))
            });
            if (this.isStatusCodeValid(resp.status)) {
                return true;
            } else if (this.shouldStatusCodeRetry(resp.status)) {
                return await retryRequest(`invalid status code ${resp.status}`);
            } else {
                throw new Error(`invalid status code ${resp.status}`);
            }
        } catch (e) {
            if (e.name === 'TimeoutError') {
                return await retryRequest(
                    `request timed out after ${DD_REQUEST_TIMEOUT_MS}ms`
                );
            } else {
                return await retryRequest(e.message);
            }
        }
    }
}

class Scrubber {
    /**
     * @param {InvocationContext} context
     * @param {Record<string, {'pattern': string, 'replacement': string}>} configs
     */
    constructor(context, configs) {
        let rules = [];
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
                context.error(
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
    /**
     * @param {InvocationContext} context
     */
    constructor(context) {
        this.context = context;
        this.logSplittingConfig = getLogSplittingConfig();
        this.records = [];
    }

    findSplitRecords(record, fields) {
        let tempRecord = record;
        for (const fieldIndex in fields) {
            const fieldName = fields[fieldIndex];
            // loop through the fields to find the one we want to split
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
            let originalRecord = this.addTagsToJsonLog(record);
            // normalize the host field. Azure EventHub sends it as "Host".
            if (originalRecord.Host) {
                originalRecord.host = originalRecord.Host;
            }
            let source = originalRecord['ddsource'];
            let config = this.logSplittingConfig[source];
            if (config !== undefined) {
                let splitFieldFound = false;

                for (const fields of config.paths) {
                    let recordsToSplit = this.findSplitRecords(record, fields);
                    if (
                        recordsToSplit === null ||
                        !(recordsToSplit instanceof Array)
                    ) {
                        // if we were unable find the field or if the field isn't an array, skip it
                        continue;
                    }
                    splitFieldFound = true;

                    for (let splitRecord of recordsToSplit) {
                        if (typeof splitRecord === 'string') {
                            try {
                                splitRecord = JSON.parse(splitRecord);
                            } catch {}
                        }
                        let formattedSplitRecord = {};
                        let temp = formattedSplitRecord;
                        // re-create the same nested attributes with only the split log
                        for (let k = 0; k < fields.length; k++) {
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
                        let newRecord;
                        if (config.preserve_fields) {
                            newRecord = { ...originalRecord };
                        } else {
                            newRecord = {
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
        let logsType = this.getLogFormat(logs);
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
                this.context.error('Log format is invalid: ', logs);
                break;
            default:
                this.context.error('Log format is invalid: ', logs);
                break;
        }
        return this.records;
    }

    handleJSONArrayLogs(logs, logsType) {
        for (let message of logs) {
            if (logsType == JSON_STRING_ARRAY) {
                try {
                    message = JSON.parse(message);
                } catch {
                    this.context.warn(
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
                } catch {
                    this.context.warn(
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
        } catch {
            return false;
        }
    }

    createDDTags(tags) {
        const forwarderNameTag =
            'forwardername:' + this.context.functionName;
        const fowarderVersionTag = 'forwarderversion:' + VERSION;
        let ddTags = tags.concat([
            DD_TAGS,
            forwarderNameTag,
            fowarderVersionTag
        ]);
        return ddTags.filter(Boolean).join(',');
    }

    addTagsToJsonLog(record) {
        let [metadata, newRecord] = this.extractMetadataFromLog(record);
        newRecord['ddsource'] = metadata.source || DD_SOURCE;
        newRecord['ddsourcecategory'] = DD_SOURCE_CATEGORY;
        newRecord['service'] = metadata.service || DD_SERVICE;
        newRecord['ddtags'] = this.createDDTags(metadata.tags);
        return newRecord;
    }

    addTagsToStringLog(stringLog) {
        let jsonLog = { message: stringLog };
        return this.addTagsToJsonLog(jsonLog);
    }

    createResourceIdArray(resourceId) {
        // Convert a valid resource ID to an array, handling beginning/ending slashes
        let resourceIdArray = resourceId.toLowerCase().split('/');
        if (resourceIdArray[0] === '') {
            resourceIdArray = resourceIdArray.slice(1);
        }
        if (resourceIdArray[resourceIdArray.length - 1] === '') {
            resourceIdArray.pop();
        }
        return resourceIdArray;
    }

    isSource(resourceIdPart) {
        // Determine if a section of a resource ID counts as a "source," in our case it means it starts with 'microsoft.'
        return resourceIdPart.startsWith('microsoft.');
    }

    formatSourceType(sourceType) {
        return sourceType.replace('microsoft.', 'azure.');
    }

    getResourceId(record) {
        // Most logs have resourceId, but some logs have ResourceId instead
        let id = record.resourceId || record.ResourceId;
        if (typeof id !== 'string') {
            return null;
        }
        return id;
    }

    extractMetadataFromLog(record) {
        if (shouldParseDefenderForCloudLogs() && this.isDefenderForCloudLog(record)) {
            return this.extractMetadataFromDefenderLog(record);
        }
        return [this.extractMetadataFromStandardLog(record), record];
    }

    extractMetadataFromStandardLog(record) {
        let metadata = { tags: [], source: '', service: '' };
        let resourceId = this.getResourceId(record);
        if (resourceId === null || resourceId === '') {
            return metadata;
        }
        resourceId = this.createResourceIdArray(resourceId);

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

    getDefenderForCloudLogType(record) {
        return record.type || record.Type;
    }

    isDefenderForCloudLog(record) {
        const productName = record.ProductName;
        const type = this.getDefenderForCloudLogType(record);
        return DEFENDER_FOR_CLOUD_PRODUCTS.includes(productName) || DEFENDER_FOR_CLOUD_RESOURCE_TYPES.includes(type);
    }

    removeWhitespaceFromKeys(obj) {
        // remove whitespace from the keys of an object and capitalizes the letter that follows
        let newObj = {};
        for (const [key, value] of Object.entries(obj)) {
            // regex looks for word boundaries and captures the alpha character that follows
            const newKey = key
                .replace(/\b\w/g, c => c.toUpperCase())
                .replaceAll(' ', '');
            newObj[newKey] = value;
        }
        return newObj;
    }

    extractMetadataFromDefenderLog(record) {
        var metadata = { tags: [], source: 'microsoft-defender-for-cloud', service: '' };
        const productName = record.ProductName;
        const type = this.getDefenderForCloudLogType(record);

        if (DEFENDER_FOR_CLOUD_PRODUCTS.includes(productName)) {
            metadata.service = 'SecurityAlerts';
            const extendedProperties = record.ExtendedProperties || {};
            record.ExtendedProperties = this.removeWhitespaceFromKeys(extendedProperties);
        } else if ([SECURITY_ASSESSMENTS, SECURITY_COMPLIANCE_ASSESSMENTS].includes(type)) {
            metadata.service = 'SecurityRecommendations';
        } else if (type === SECURITY_SUB_ASSESSMENTS) {
            metadata.service = 'SecurityFindings';
        } else if ([SECURITY_SCORES, SECURITY_SCORE_CONTROLS].includes(type)) {
            metadata.service = 'SecureScore';
        } else {
            metadata.service = 'microsoft-defender-for-cloud';
        }
        return [metadata, record];
    }
}

app.eventHub('datadog-function', {
    trigger: {
        type: 'eventHubTrigger',
        name: 'eventHubMessages',
        eventHubName: 'datadog-eventhub',
        connection: 'EVENTHUB_CONNECTION_STRING',
        cardinality: 'many',
        consumerGroup: '$Default',
        direction: 'in'
    },
    handler: async (eventHubMessages, context) => {
        
        if (!DD_API_KEY || DD_API_KEY === '<DATADOG_API_KEY>') {
            context.error(
                'You must configure your API key before starting this function (see ## Parameters section)'
            );
            return;
        }
        let parsedLogs;
        try {
            let handler = new EventhubLogHandler(context);
            parsedLogs = handler.handleLogs(eventHubMessages);
        } catch (err) {
            context.error('Error raised when parsing logs: ', err);
            throw err;
        }
        let results = await new HTTPClient(context).sendAll(parsedLogs);

        if (results.every(v => v === true) !== true) {
            context.error(
                'Some messages were unable to be sent. See other logs for details.'
            );
        }
    }
});

module.exports.forTests = {
    EventhubLogHandler,
    Scrubber,
    ScrubberRule,
    Batcher,
    HTTPClient,
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
