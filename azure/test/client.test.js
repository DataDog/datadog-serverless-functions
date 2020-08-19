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

var EventhubLogForwarderInstance = new client.EventhubLogForwarder(
    fakeContext()
);
EventhubLogForwarderInstance.sendWithRetry = function(record) {}; // do nothing
console.log(EventhubLogForwarderInstance.getLogFormat);
var handleJsonLogsSpy = sinon.spy();
var handleStringLogsSpy = sinon.spy();

EventhubLogForwarderInstance.addTagsToJsonLog = handleJsonLogsSpy;
EventhubLogForwarderInstance.addTagsToStringLog = handleStringLogsSpy;

describe('Azure Log Monitoring', function() {
    describe('#getLogFormat', function() {
        it('should return string', function() {
            eventHubMessages = '';
            assert.equal(
                constants.STRING,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
            eventHubMessages = 'foobar';
            assert.equal(
                constants.STRING,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
        });
        it('should return string array', function() {
            eventHubMessages = ['', 'foobar'];
            assert.equal(
                constants.STRING_ARRAY,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
        });
        it('should return json object', function() {
            eventHubMessages = { key: 'value', otherkey: 'othervalue' };
            assert.equal(
                constants.JSON_OBJECT,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
        });
        it('should return json array when there are no records', function() {
            eventHubMessages = [
                { key: 'value', otherkey: 'othervalue' },
                { key: 'value', otherkey: 'othervalue' }
            ];
            assert.equal(
                constants.JSON_ARRAY,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
        });
        it('should return invalid', function() {
            eventHubMessages = 1;
            assert.equal(
                constants.INVALID,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
            eventHubMessages = () => {};
            assert.equal(
                constants.INVALID,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
            eventHubMessages = true;
            assert.equal(
                constants.INVALID,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
            eventHubMessages = null;
            assert.equal(
                constants.INVALID,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
            eventHubMessages = undefined;
            assert.equal(
                constants.INVALID,
                EventhubLogForwarderInstance.getLogFormat(eventHubMessages)
            );
        });
    });

    describe('#extractResourceId', function() {
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
                EventhubLogForwarderInstance.extractResourceId(record)
            );
        });
        it('should parse a valid record without provider', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP'
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
                EventhubLogForwarderInstance.extractResourceId(record)
            );
        });
        it('should parse a valid record without provider and resource group', function() {
            record = {
                resourceId:
                    '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB'
            };
            expectedMetadata = {
                tags: ['subscription_id:12345678-1234-abcd-1234-1234567890ab'],
                source: ''
            };
            assert.deepEqual(
                expectedMetadata,
                EventhubLogForwarderInstance.extractResourceId(record)
            );
        });
        it('should not fail on record without resourceId', function() {
            record = { key: 'value' };
            expectedMetadata = { tags: [], source: '' };
            assert.deepEqual(
                expectedMetadata,
                EventhubLogForwarderInstance.extractResourceId(record)
            );
        });
        it('should not fail on string record', function() {
            record = { key: 'value' };
            expectedMetadata = { tags: [], source: '' };
            assert.deepEqual(
                expectedMetadata,
                EventhubLogForwarderInstance.extractResourceId(record)
            );
        });
        it('should not fail on improper resourceId', function() {
            record = { resourceId: 'foo/bar' };
            expectedMetadata = { tags: [], source: '' };
            assert.deepEqual(
                expectedMetadata,
                EventhubLogForwarderInstance.extractResourceId(record)
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
                EventhubLogForwarderInstance.extractResourceId(record)
            );
        });
    });

    function testHandleLogs(logs, expected, assertJson) {
        EventhubLogForwarderInstance.handleLogs(record);
        if (assertJson == true) {
            expected.forEach(message => {
                sinon.assert.calledWith(handleJsonLogsSpy, message);
            });
        } else {
            expected.forEach(message => {
                sinon.assert.calledWith(handleStringLogsSpy, message);
            });
        }
    }

    describe('#handleLogs', function() {
        it('should handle string properly', function() {
            record = 'hello';
            expected = ['hello'];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.STRING
            );
            testHandleLogs(record, expected, false);
        });

        it('should handle json-string properly', function() {
            record = '{"hello": "there"}';
            expected = [{ hello: 'there' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.JSON_STRING
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle json-object properly', function() {
            record = { hello: 'there' };
            expected = [{ hello: 'there' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.JSON_OBJECT
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle string-array properly', function() {
            record = ['one message', 'two message'];
            expected = ['one message', 'two message'];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.STRING_ARRAY
            );
            testHandleLogs(record, expected, false);
        });

        it('should handle json-records properly', function() {
            record = [{ records: [{ hello: 'there' }, { goodbye: 'now' }] }];
            expected = [{ hello: 'there' }, { goodbye: 'now' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.JSON_ARRAY
            ); //JSON_RECORDS
            testHandleLogs(record, expected, true);
        });

        it('should handle json-array properly', function() {
            record = [{ hello: 'there' }, { goodbye: 'now' }];
            expected = [{ hello: 'there' }, { goodbye: 'now' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.JSON_ARRAY
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle buffer array properly', function() {
            record = [Buffer.from('{"records": [{ "test": "testing"}]}')];
            expected = [{ test: 'testing' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.BUFFER_ARRAY
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle buffer array without records properly', function() {
            record = [Buffer.from('{[{ "test": "testing"}]}')];
            expected = [{ test: 'testing' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.BUFFER_ARRAY
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle buffer array without records properly', function() {
            record = [Buffer.from('{[{ "test": "testing"}]}')];
            expected = [{ test: 'testing' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.BUFFER_ARRAY
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle buffer array with malformed string', function() {
            record = [Buffer.from('{"time": "xy')];
            expected = ['{"time": "xy'];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.BUFFER_ARRAY
            );
            // just assert that the string method is called for the second message,
            // we don't care about the first one for this test
            testHandleLogs(record, expected, false);
        });

        it('should handle json-string-array properly records', function() {
            record = ['{"records": [{ "time": "xyz"}, {"time": "abc"}]}'];
            expected = [{ time: 'xyz' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.JSON_STRING_ARRAY
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle json-string-array properly no records', function() {
            record = ['{"time": "xyz"}'];
            expected = [{ time: 'xyz' }];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.JSON_STRING_ARRAY
            );
            testHandleLogs(record, expected, true);
        });

        it('should handle json-string-array with malformed string', function() {
            record = ['{"time": "xyz"}', '{"time": "xy'];
            expected = ['{"time": "xy'];
            assert.equal(
                EventhubLogForwarderInstance.getLogFormat(record),
                constants.JSON_STRING_ARRAY
            );
            // just assert that the string method is called for the second message,
            // we don't care about the first one for this test
            testHandleLogs(record, expected, false);
        });
    });
});
