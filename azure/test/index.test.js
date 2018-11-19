var assert = require('assert');
var azure = require('../activity_logs_monitoring').forTests;

describe('Azure Log Monitoring', function() {
  describe('#getEventHubMessagesFormat', function() {
    it('should return string', function() {
        eventHubMessages = '';
        assert.equal(azure.STRING, azure.getEventHubMessagesFormat(eventHubMessages));
        eventHubMessages = 'foobar';
        assert.equal(azure.STRING, azure.getEventHubMessagesFormat(eventHubMessages));
    });
    it('should return string array', function() {
      eventHubMessages = ['', 'foobar'];
      assert.equal(azure.STRING_ARRAY, azure.getEventHubMessagesFormat(eventHubMessages));
    });
    it('should return json with records', function() {
      eventHubMessages = [{'records': [{}, {}]}, {'records': [{}, {}]}];
      assert.equal(azure.JSON_RECORDS, azure.getEventHubMessagesFormat(eventHubMessages));
    });
    it('should return json object', function() {
      eventHubMessages = {'key': 'value', 'otherkey':'othervalue'};
      assert.equal(azure.JSON_OBJECT, azure.getEventHubMessagesFormat(eventHubMessages));
    });
    it('should return json no records', function() {
      eventHubMessages = [{'key': 'value', 'otherkey':'othervalue'}, {'key': 'value', 'otherkey':'othervalue'}];
      assert.equal(azure.JSON_ARRAY, azure.getEventHubMessagesFormat(eventHubMessages));
    });
    it('should return invalid', function() {
      eventHubMessages = 1;
      assert.equal(azure.INVALID, azure.getEventHubMessagesFormat(eventHubMessages));
      eventHubMessages = () => {};
      assert.equal(azure.INVALID, azure.getEventHubMessagesFormat(eventHubMessages));
      eventHubMessages = true;
      assert.equal(azure.INVALID, azure.getEventHubMessagesFormat(eventHubMessages));
      eventHubMessages = null;
      assert.equal(azure.INVALID, azure.getEventHubMessagesFormat(eventHubMessages));
      eventHubMessages = undefined;
      assert.equal(azure.INVALID, azure.getEventHubMessagesFormat(eventHubMessages));
    });
  });

  describe('#extractResourceId', function() {
    it('should parse a valid record', function() {
      record = {'resourceId': '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/PROVIDERS/MICROSOFT.COMPUTE/VIRTUALMACHINES/SOME-VM'}
      expectedMetadata = {'tags': ["subscription_id:12345678-1234-abcd-1234-1234567890ab","resource_group:some-resource-group"], 'source': 'azure.compute'}
      assert.deepEqual(expectedMetadata, azure.extractResourceId(record))
    });
    it('should parse a valid record without provider', function() {
      record = {'resourceId': '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP'}
      expectedMetadata = {'tags': ["subscription_id:12345678-1234-abcd-1234-1234567890ab","resource_group:some-resource-group"], 'source': ''}
      assert.deepEqual(expectedMetadata, azure.extractResourceId(record))
    });
    it('should parse a valid record without provider and resource group', function() {
      record = {'resourceId': '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB'}
      expectedMetadata = {'tags': ["subscription_id:12345678-1234-abcd-1234-1234567890ab"], 'source': ''}
      assert.deepEqual(expectedMetadata, azure.extractResourceId(record))
    });
    it('should not fail on record without resourceId', function() {
      record = {'key':'value'}
      expectedMetadata = {'tags': [], 'source': ''}
      assert.deepEqual(expectedMetadata, azure.extractResourceId(record))
    });
    it('should not fail on string record', function() {
      record = {'key':'value'}
      expectedMetadata = {'tags': [], 'source': ''}
      assert.deepEqual(expectedMetadata, azure.extractResourceId(record))
    });
    it('should not fail on improper resourceId', function() {
      record = {'resourceId': 'foo/bar'}
      expectedMetadata = {'tags': [], 'source': ''}
      assert.deepEqual(expectedMetadata, azure.extractResourceId(record))
    });
  })
});
