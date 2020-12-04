var assert = require('assert');
var client = require('../activity_logs_monitoring').forTests;
var constants = client.constants;
var sinon = require('sinon');

function fakeContext() {
    // create a fake context object to pass into handleLogs
    contextSpy = sinon.spy();
    contextSpy.log = sinon.spy();
    contextSpy.log.error = function(x) {}; // do nothing
    contextSpy.log.warn = function(x) {}; // do nothing

    return contextSpy;
}

function setUp() {
    var forwarder = new client.EventhubLogForwarder(fakeContext());
    forwarder.sendWithRetry = function(record) {}; // do nothing

    forwarder.addTagsToJsonLog = sinon.spy();
    forwarder.addTagsToStringLog = sinon.spy();
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

describe('Azure Log Monitoring', function() {
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

    describe('#extractMetadataFromResource', function() {
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
                source: 'azure.compute'
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
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
                source: 'azure.resourcegroup'
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
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
                source: 'azure.resourcegroup'
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
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
                source: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
        it('should parse a valid subscription type resource', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: 'azure.subscription'
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
        it('should parse a valid subscription type resource ending slash', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: 'azure.subscription'
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
        it('should parse a valid record without provider and resource group length 3', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/ffffff'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
        it('should not fail on record without resourceId', function() {
            record = { key: 'value' };
            expectedMetadata = { tags: [], source: '' };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
        it('should not fail on string record', function() {
            record = { key: 'value' };
            expectedMetadata = { tags: [], source: '' };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
        it('should not fail on improper resourceId', function() {
            record = { resourceId: 'foo/bar' };
            expectedMetadata = { tags: [], source: '' };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
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
                source: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
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
                source: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
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
                source: ''
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
        it('should correctly parse provider-only resource ids', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/PROVIDERS/MICROSOFT.RECOVERYSERVICES/SOMETHING/SOMETHINGELSE'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: 'azure.recoveryservices'
            };
            assert.deepEqual(
                expectedMetadata,
                this.forwarder.extractMetadataFromResource(record)
            );
        });
    });

    function testHandleJSONLogs(forwarder, logs, expected) {
        forwarder.handleLogs(logs);
        expected.forEach(message => {
            sinon.assert.calledWith(forwarder.addTagsToJsonLog, message);
        });
    }

    function testHandleStringLogs(forwarder, logs, expected) {
        forwarder.handleLogs(logs);
        expected.forEach(message => {
            sinon.assert.calledWith(forwarder.addTagsToStringLog, message);
        });
    }

    describe('#handleLogs', function() {
        beforeEach(function() {
            this.forwarder = setUp();
        });

        it('should handle string properly', function() {
            log = 'hello';
            expected = ['hello'];
            assert.equal(this.forwarder.getLogFormat(log), constants.STRING);
            testHandleStringLogs(this.forwarder, log, expected);
        });

        it('should handle json-string properly', function() {
            log = '{"hello": "there"}';
            expected = [{ hello: 'there' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-object properly', function() {
            log = { hello: 'there' };
            expected = [{ hello: 'there' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_OBJECT
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle string-array properly', function() {
            log = ['one message', 'two message'];
            expected = ['one message', 'two message'];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.STRING_ARRAY
            );
            testHandleStringLogs(this.forwarder, log, expected);
        });

        it('should handle json-records properly', function() {
            log = [{ records: [{ hello: 'there' }, { goodbye: 'now' }] }];
            expected = [{ hello: 'there' }, { goodbye: 'now' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_ARRAY
            ); //JSON_RECORDS
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-array properly', function() {
            log = [{ hello: 'there' }, { goodbye: 'now' }];
            expected = [{ hello: 'there' }, { goodbye: 'now' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle buffer array properly', function() {
            log = [Buffer.from('{"records": [{ "test": "testing"}]}')];
            expected = [{ test: 'testing' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.BUFFER_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle buffer array without records properly', function() {
            log = [Buffer.from('{ "test": "example"}')];
            expected = [{ test: 'example' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.BUFFER_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle buffer array with malformed string', function() {
            log = [Buffer.from('{"time": "xy')];
            expected = ['{"time": "xy'];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.BUFFER_ARRAY
            );
            testHandleStringLogs(this.forwarder, log, expected);
        });

        it('should handle json-string-array properly records', function() {
            log = ['{"records": [{ "time": "xyz"}, {"time": "abc"}]}'];
            expected = [{ time: 'xyz' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-string-array properly no records', function() {
            log = ['{"time": "xyz"}'];
            expected = [{ time: 'xyz' }];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING_ARRAY
            );
            testHandleJSONLogs(this.forwarder, log, expected);
        });

        it('should handle json-string-array with malformed string', function() {
            log = ['{"time": "xyz"}', '{"time": "xy'];
            expected = ['{"time": "xy'];
            assert.equal(
                this.forwarder.getLogFormat(log),
                constants.JSON_STRING_ARRAY
            );
            // just assert that the string method is called for the second message,
            // we don't care about the first one for this test
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
