const assert = require('assert');
const client = require('../activity_logs_monitoring').forTests;
const constants = client.constants;
const sinon = require('sinon');
const { InvocationContext } = require('@azure/functions');

function fakeContext() {
    return new InvocationContext({
        functionName: 'testFunctionName',
        invocationId: 'testInvocationId'
    });
}

function setUp() {
    const forwarder = new client.EventhubLogHandler(fakeContext());

    forwarder.addTagsToJsonLog = x => {
        return Object.assign({ ddsource: 'none' }, x);
    };
    forwarder.addTagsToStringLog = x => {
        return { ddsource: 'none', message: x };
    };

    return forwarder;
}

const DEFAULT_TEST_SCRUBBER_RULES = {
    REDACT_IP: {
        pattern: /[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/,
        replacement: 'xxx.xxx.xxx.xxx'
    },
    REDACT_EMAIL: {
        pattern: /[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/,
        replacement: 'xxxxx@xxxxx.com'
    }
};

describe('Azure Activity Log Monitoring', function() {
    describe('#getLogFormat', function() {
        beforeEach(function() {
            this.forwarder = setUp();
        });
        it('should return string', function() {
            eventHubMessages = '';
            assert.equal(
                constants.STRING,
                this.forwarder.getLogFormat(eventHubMessages)
            );
            eventHubMessages = 'foobar';
            assert.equal(
                constants.STRING,
                this.forwarder.getLogFormat(eventHubMessages)
            );
        });
        it('should return string array', function() {
            eventHubMessages = ['', 'foobar'];
            assert.equal(
                constants.STRING_ARRAY,
                this.forwarder.getLogFormat(eventHubMessages)
            );
        });
        it('should return json object', function() {
            eventHubMessages = { key: 'value', otherkey: 'othervalue' };
            assert.equal(
                constants.JSON_OBJECT,
                this.forwarder.getLogFormat(eventHubMessages)
            );
        });
        it('should return json array when there are no records', function() {
            eventHubMessages = [
                { key: 'value', otherkey: 'othervalue' },
                { key: 'value', otherkey: 'othervalue' }
            ];
            assert.equal(
                constants.JSON_ARRAY,
                this.forwarder.getLogFormat(eventHubMessages)
            );
        });
        it('should return invalid', function() {
            eventHubMessages = 1;
            assert.equal(
                constants.INVALID,
                this.forwarder.getLogFormat(eventHubMessages)
            );
            eventHubMessages = () => {};
            assert.equal(
                constants.INVALID,
                this.forwarder.getLogFormat(eventHubMessages)
            );
            eventHubMessages = true;
            assert.equal(
                constants.INVALID,
                this.forwarder.getLogFormat(eventHubMessages)
            );
            eventHubMessages = null;
            assert.equal(
                constants.INVALID,
                this.forwarder.getLogFormat(eventHubMessages)
            );
            eventHubMessages = undefined;
            assert.equal(
                constants.INVALID,
                this.forwarder.getLogFormat(eventHubMessages)
            );
        });
    });

    describe('#extractMetadataFromLog', function() {
        beforeEach(function() {
            this.forwarder = setUp();
        });
        it('should parse a valid record', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/PROVIDERS/MICROSOFT.COMPUTE/VIRTUALMACHINES/SOME-VM'
            };
            expectedMetadata = {
                tags: [
                    'subscription_id:12345678-1234-abcd-1234-1234567890ab',
                    'resource_group:some-resource-group'
                ],
                source: 'azure.compute',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should parse a valid resource group resource', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP'
            };
            expectedMetadata = {
                tags: [
                    'subscription_id:12345678-1234-abcd-1234-1234567890ab',
                    'resource_group:some-resource-group'
                ],
                source: 'azure.resourcegroup',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should parse a valid resource group resource ending slash', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/'
            };
            expectedMetadata = {
                tags: [
                    'subscription_id:12345678-1234-abcd-1234-1234567890ab',
                    'resource_group:some-resource-group'
                ],
                source: 'azure.resourcegroup',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should parse a valid record without provider length 5', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/ffffff'
            };
            expectedMetadata = {
                tags: [
                    'subscription_id:12345678-1234-abcd-1234-1234567890ab',
                    'resource_group:some-resource-group'
                ],
                source: '',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should parse a valid subscription type resource', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: 'azure.subscription',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should parse a valid subscription type resource ending slash', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: 'azure.subscription',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should parse a valid record without provider and resource group length 3', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/ffffff'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: '',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should not fail on record without resourceId', function() {
            record = { key: 'value' };
            expectedMetadata = { tags: [], source: '', service: '' };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should not fail on string record', function() {
            record = { key: 'value' };
            expectedMetadata = { tags: [], source: '', service: '' };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should not fail on improper resourceId', function() {
            record = { resourceId: 'foo/bar' };
            expectedMetadata = { tags: [], source: '', service: '' };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should not fail with an invalid source', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/PROVIDERS/////'
            };
            expectedMetadata = {
                tags: [
                    'subscription_id:12345678-1234-abcd-1234-1234567890ab',
                    'resource_group:some-resource-group'
                ],
                source: '',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should return empty source when not correct source format', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/PROVIDERS/NOTTHESAMEFORMAT/VIRTUALMACHINES/SOME-VM'
            };
            expectedMetadata = {
                tags: [
                    'subscription_id:12345678-1234-abcd-1234-1234567890ab',
                    'resource_group:some-resource-group'
                ],
                source: '',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should handle when first element of resource id list is not empty', function() {
            record = {
                resourceId:
                    'SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/PROVIDERS/NOTTHESAMEFORMAT/VIRTUALMACHINES/SOME-VM'
            };
            expectedMetadata = {
                tags: [
                    'subscription_id:12345678-1234-abcd-1234-1234567890ab',
                    'resource_group:some-resource-group'
                ],
                source: '',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
        it('should correctly parse provider-only resource ids', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/PROVIDERS/MICROSOFT.RECOVERYSERVICES/SOMETHING/SOMETHINGELSE'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: 'azure.recoveryservices',
                service: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromLog(record)[0]
            );
        });
    });

    function testHandleJSONLogs(forwarder, logs, expected) {
        actual = forwarder.handleLogs(logs);
        assert.deepEqual(actual, expected);
    }

    function testHandleStringLogs(forwarder, logs, expected) {
        actual = forwarder.handleLogs(logs);
        assert.deepEqual(actual, expected);
    }

    describe('#handleLogs', function() {
        beforeEach(function() {
            this.forwarder = setUp();
        });

        it('should handle string properly', function() {
            log = 'hello';
            expected = [{ ddsource: 'none', message: 'hello' }];
            assert.equal(this.forwarder.getLogFormat(log), constants.STRING);
            testHandleStringLogs(this.forwarder, log, expected);
        });

        it('should handle json-string properly', function() {
            log = '{"hello": "there"}';
            expected = [{ ddsource: 'none', hello: 'there' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-object properly', function() {
            log = { hello: 'there' };
            expected = [{ ddsource: 'none', hello: 'there' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_OBJECT
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle string-array properly', function() {
            log = ['one message', 'two message'];
            expected = [
                { ddsource: 'none', message: 'one message' },
                { ddsource: 'none', message: 'two message' }
            ];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.STRING_ARRAY
            );
            testHandleStringLogs(this.forwarder, log, expected);
        });

        it('should handle json-records properly', function() {
            log = [{ records: [{ hello: 'there' }, { goodbye: 'now' }] }];
            expected = [
                { ddsource: 'none', hello: 'there' },
                { ddsource: 'none', goodbye: 'now' }
            ];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_ARRAY
            ); //JSON_RECORDS
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-array properly', function() {
            log = [{ hello: 'there' }, { goodbye: 'now' }];
            expected = [
                { ddsource: 'none', hello: 'there' },
                { ddsource: 'none', goodbye: 'now' }
            ];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle buffer array properly', function() {
            log = [Buffer.from('{"records": [{ "test": "testing"}]}')];
            expected = [{ ddsource: 'none', test: 'testing' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.BUFFER_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle buffer array without records properly', function() {
            log = [Buffer.from('{ "test": "example"}')];
            expected = [{ ddsource: 'none', test: 'example' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.BUFFER_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle buffer array with malformed string', function() {
            log = [Buffer.from('{"time": "xy')];
            expected = [{ ddsource: 'none', message: '{"time": "xy' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.BUFFER_ARRAY
            );
            testHandleStringLogs(this.forwarder, log, expected);
        });

        it('should handle json-string-array properly records', function() {
            log = ['{"records": [{ "time": "xyz"}, {"time": "abc"}]}'];
            expected = [
                { ddsource: 'none', time: 'xyz' },
                { ddsource: 'none', time: 'abc' }
            ];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-string-array properly no records', function() {
            log = ['{"time": "xyz"}'];
            expected = [{ ddsource: 'none', time: 'xyz' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-string-array with malformed string', function() {
            log = ['{"time": "xyz"}', '{"time": "xy'];
            expected = [
                { ddsource: 'none', time: 'xyz' },
                { ddsource: 'none', message: '{"time": "xy' }
            ];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING_ARRAY
            );
            testHandleStringLogs(this.forwarder, log, expected);
        });
    });
    describe('#formatSourceType', function() {
        beforeEach(function() {
            this.forwarder = setUp();
        });
        it('should replace microsoft with azure', function() {
            expected = 'azure.bleh';
            actual = this.forwarder.formatSourceType('microsoft.bleh');
            assert.equal(actual, expected);
        });
    });
    describe('#scrubPII', function() {
        it('should set up configs correctly', function() {
            test_rules = {
                REDACT_IP: {
                    pattern: '[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}',
                    replacement: 'xxx.xxx.xxx.xxx'
                }
            };
            scrubber = new client.Scrubber(fakeContext(), test_rules);
            rule = scrubber.rules[0];
            assert.equal(rule instanceof client.ScrubberRule, true);
            assert.equal(rule.name, 'REDACT_IP');
            assert.equal(rule.regexp instanceof RegExp, true);
            assert.equal(rule.replacement, 'xxx.xxx.xxx.xxx');
        });
        it('should scrub email from record', function() {
            expected = 'sender_email: xxxxx@xxxxx.com';
            scrubber = new client.Scrubber(
                fakeContext(),
                DEFAULT_TEST_SCRUBBER_RULES
            );
            actual = scrubber.scrub('sender_email: hello@test.com');
            assert.equal(actual, expected);
        });
        it('should scrub ip address from record', function() {
            expected = 'client_ip: xxx.xxx.xxx.xxx';
            scrubber = new client.Scrubber(
                fakeContext(),
                DEFAULT_TEST_SCRUBBER_RULES
            );
            actual = scrubber.scrub('client_ip: 12.123.23.12');
            assert.equal(actual, expected);
        });
        it('should scrub ip address and email from record', function() {
            expected = 'client_ip: xxx.xxx.xxx.xxx, email: xxxxx@xxxxx.com';
            scrubber = new client.Scrubber(
                fakeContext(),
                DEFAULT_TEST_SCRUBBER_RULES
            );
            actual = scrubber.scrub(
                'client_ip: 12.123.23.12, email: hello@test.com'
            );
            assert.equal(actual, expected);
        });
        it('should scrub multiple ip address from string', function() {
            expected =
                'client_ip: xxx.xxx.xxx.xxx, client_ip2: xxx.xxx.xxx.xxx';
            scrubber = new client.Scrubber(
                fakeContext(),
                DEFAULT_TEST_SCRUBBER_RULES
            );
            actual = scrubber.scrub(
                'client_ip: 12.123.23.12, client_ip2: 122.123.213.112'
            );
            assert.equal(actual, expected);
        });
        it('should scrub multiple ip address and email from string', function() {
            expected =
                'client_ip: xxx.xxx.xxx.xxx, client_ip2: xxx.xxx.xxx.xxx email: xxxxx@xxxxx.com email2: xxxxx@xxxxx.com';
            scrubber = new client.Scrubber(
                fakeContext(),
                DEFAULT_TEST_SCRUBBER_RULES
            );
            actual = scrubber.scrub(
                'client_ip: 12.123.23.12, client_ip2: 122.123.213.112 email: hello@test.com email2: hello2@test.com'
            );
            assert.equal(actual, expected);
        });
        it('should handle malformed regexp correctly', function() {
            // we don't want to break if we have a malformed regex, just want to skip it until the user fixes it
            test_rules = {
                REDACT_SOMETHING: {
                    pattern: '[2-',
                    replacement: 'xxx.xxx.xxx.xxx'
                }
            };
            scrubber = new client.Scrubber(fakeContext(), test_rules);
            assert.equal(scrubber.rules.length, 0);
        });
        it('should not scrub when there are no rules defined', function() {
            // if there are no rules, then the log should be the same before and after
            test_rules = {};
            expected =
                'client_ip: 12.123.23.12, client_ip2: 122.123.213.112 email: hello@test.com email2: hello2@test.com';
            scrubber = new client.Scrubber(fakeContext(), test_rules);
            actual = scrubber.scrub(
                'client_ip: 12.123.23.12, client_ip2: 122.123.213.112 email: hello@test.com email2: hello2@test.com'
            );
            assert.equal(actual, expected);
        });
    });
});

describe('Batching', function() {
    describe('#batch', function() {
        it('should return two batches because of size', function() {
            batcher = new client.Batcher(15, 15, 1);
            logs = [{ hi: 'bye' }, 'bleh'];
            actual = batcher.batch(logs);
            expected = [[{ hi: 'bye' }], ['bleh']];
            assert.deepEqual(actual, expected);
        });
        it('should return two batches because of batch size bytes', function() {
            batcher = new client.Batcher(15, 12, 10);
            logs = [{ hi: 'bye' }, 'bleh'];
            actual = batcher.batch(logs);
            expected = [[{ hi: 'bye' }], ['bleh']];
            assert.deepEqual(actual, expected);
        });
        it('should drop message based on message bytes size', function() {
            batcher = new client.Batcher(5, 5, 1);
            logs = [{ hi: 'bye' }, 'bleh'];
            actual = batcher.batch(logs);
            expected = [['bleh']];
            assert.deepEqual(actual, expected);
        });
    });
    describe('#getSizeInBytes', function() {
        it('should return 5 for string', function() {
            batcher = new client.Batcher(15, 15, 1);
            log = 'aaaaa';
            actual = batcher.getSizeInBytes(log);
            expected = 5;
            assert.equal(actual, expected);
        });

        it('should return 7 for object', function() {
            batcher = new client.Batcher(15, 15, 1);
            log = { a: 2 };
            actual = batcher.getSizeInBytes(log);
            expected = 7;
            assert.equal(actual, expected);
        });
    });
});

describe('HTTPClient', function() {
    let clientContext;
    let httpClient;
    beforeEach(function() {
        clientContext = fakeContext();
        clientContext.error = sinon.spy();
        clientContext.warn = sinon.spy();
        httpClient = new client.HTTPClient(clientContext);
    });

    describe('#sendAll', function() {
        it('should log any errors that occur when sending logs', async function() {
            const err = new Error('some error in the API');
            httpClient.send = sinon.stub().rejects(err);
            httpClient.batcher.batch = sinon
                .stub()
                .returns([{ batch: 'batch1' }, { batch: 'batch2' }]);
            await httpClient.sendAll([]); // we mock out the batcher so this argument doesnt matter
            assert.equal(clientContext.error.callCount, 2);
            assert(clientContext.error.calledWith(err));
        });
    });
});

describe('Log Splitting', function() {
    function setUpWithLogSplittingConfig(config) {
        const forwarder = new client.EventhubLogHandler(fakeContext());
        
        // Mock the log splitting configuration
        forwarder.logSplittingConfig = config;
        
        // Mock addTagsToJsonLog to set ddsource for testing
        forwarder.addTagsToJsonLog = x => {
            return Object.assign({ 
                ddsource: 'azure.datafactory',
                ddsourcecategory: 'azure',
                service: 'azure',
                ddtags: 'forwardername:testFunctionName'
            }, x);
        };
        
        forwarder.addTagsToStringLog = x => {
            return { 
                ddsource: 'azure.datafactory',
                ddsourcecategory: 'azure',
                service: 'azure',
                ddtags: 'forwardername:testFunctionName',
                message: x 
            };
        };

        return forwarder;
    }

    describe('#logSplitting with azure.datafactory configuration', function() {
        beforeEach(function() {
            this.testConfig = {
                'azure.datafactory': {
                    paths: [['properties', 'Output', 'value']],
                    keep_original_log: true,
                    preserve_fields: false
                }
            };
            this.forwarder = setUpWithLogSplittingConfig(this.testConfig);
        });

        it('should split logs with correct field structure due', function() {
            const inputLog = {
                resourceId: '/subscriptions/test-sub/resourceGroups/test-rg/providers/Microsoft.DataFactory/factories/test-factory',
                properties: {
                    Output: {
                        value: [
                            { id: 1, name: 'item1', status: 'success' },
                            { id: 2, name: 'item2', status: 'failed' },
                            { id: 3, name: 'item3', status: 'success' }
                        ]
                    }
                },
                timestamp: '2023-01-01T00:00:00Z',
                category: 'PipelineRuns'
            };

            const result = this.forwarder.handleLogs(inputLog);
            
            assert.equal(result.length, 4); // 3 split logs + 1 original
            assert.equal(result[0].ddsource, 'azure.datafactory');
            assert.ok(result[0].parsed_arrays);

            // the first 3 logs should be split from the array
            for (let i = 0; i < result.length -1; i++) {
                assert.equal(result[i].ddsource, 'azure.datafactory');
                assert.ok(!Array.isArray(result[i].parsed_arrays.properties['Output']['value']));
            }

            // The last log should be the original log
            assert.equal(result[3].ddsource, 'azure.datafactory');
            assert.ok(Array.isArray(result[3].properties['Output']['value']));
        });

        it('should preserve original log when path does not exist', function() {
            const inputLog = {
                properties: {
                    SomeOtherField: 'value'
                }
            };

            const result = this.forwarder.handleLogs(inputLog);
            
            // Should only have 1 log (original) since path doesn't exist
            assert.equal(result.length, 1);
            assert.equal(result[0].ddsource, 'azure.datafactory');
            assert.equal(result[0].properties.SomeOtherField, 'value');
        });

        it('should handle null/undefined values in path gracefully', function() {
            const inputLog = {
                properties: {
                    Output: null
                }
            };

            const result = this.forwarder.handleLogs(inputLog);
            
            // Should only have 1 log (original) since path leads to null
            assert.equal(result.length, 1);
            assert.equal(result[0].ddsource, 'azure.datafactory');
            assert.equal(result[0].properties.Output, null);
        });
    });

    describe('#logSplitting with non-datafactory source', function() {
        beforeEach(function() {
            this.testConfig = {
                'azure.datafactory': {
                    paths: [['properties', 'Output', 'value']],
                    keep_original_log: true,
                    preserve_fields: true
                }
            };
            this.forwarder = setUpWithLogSplittingConfig(this.testConfig);
            
            // Override to return different source
            this.forwarder.addTagsToJsonLog = x => {
                return Object.assign({ 
                    ddsource: 'azure.storage',
                    ddsourcecategory: 'azure',
                    service: 'azure',
                    ddtags: 'forwardername:testFunctionName'
                }, x);
            };
        });

        it('should not split logs from other sources', function() {
            const inputLog = {
                properties: {
                    Output: {
                        value: [
                            { id: 1, name: 'item1' },
                            { id: 2, name: 'item2' }
                        ]
                    }
                }
            };

            const result = this.forwarder.handleLogs(inputLog);
            
            // Should only have 1 log (original) since source doesn't match config
            assert.equal(result.length, 1);
            assert.equal(result[0].ddsource, 'azure.storage');
            assert.ok(!result[0].parsed_arrays);
        });
    });

    describe('#findSplitRecords method behavior', function() {
        beforeEach(function() {
            this.forwarder = new client.EventhubLogHandler(fakeContext());
        });

        it('should return an object with the field at the end of of the chain in fields', function() {
            const value = [1,2,3];
            const fields = ['properties', 'Output', 'value'];
            const record = {
                properties: {
                    Output: {
                        value: value
                    }
                }
            };

            const result = this.forwarder.findSplitRecords(record, fields);
            assert.equal(result, value);
        });

        it('should return null when path leads to null/undefined', function() {
            const fields = ['properties', 'Output', 'value'];
            const record = {
                0: null
            };

            const result = this.forwarder.findSplitRecords(record, fields);
            assert.equal(result, null);
        });
    });
});
