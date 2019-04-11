var assert = require('assert');
var client = require('../activity_logs_monitoring').forTests;
var constants = client.constants


describe('Azure Log Monitoring', function() {
  describe('#getLogFormat', function() {
    it('should return string', function() {
        eventHubMessages = '';
        assert.equal(constants.STRING, client.getLogFormat(eventHubMessages));
        eventHubMessages = 'foobar';
        assert.equal(constants.STRING, client.getLogFormat(eventHubMessages));
    });
    it('should return string array', function() {
      eventHubMessages = ['', 'foobar'];
      assert.equal(constants.STRING_ARRAY, client.getLogFormat(eventHubMessages));
    });
    it('should return json with records', function() {
      eventHubMessages = [{'records': [{}, {}]}, {'records': [{}, {}]}];
      assert.equal(constants.JSON_RECORDS, client.getLogFormat(eventHubMessages));
    });
    it('should return json object', function() {
      eventHubMessages = {'key': 'value', 'otherkey':'othervalue'};
      assert.equal(constants.JSON_OBJECT, client.getLogFormat(eventHubMessages));
    });
    it('should return json no records', function() {
      eventHubMessages = [{'key': 'value', 'otherkey':'othervalue'}, {'key': 'value', 'otherkey':'othervalue'}];
      assert.equal(constants.JSON_ARRAY, client.getLogFormat(eventHubMessages));
    });
    it('should return invalid', function() {
      eventHubMessages = 1;
      assert.equal(constants.INVALID, client.getLogFormat(eventHubMessages));
      eventHubMessages = () => {};
      assert.equal(constants.INVALID, client.getLogFormat(eventHubMessages));
      eventHubMessages = true;
      assert.equal(constants.INVALID, client.getLogFormat(eventHubMessages));
      eventHubMessages = null;
      assert.equal(constants.INVALID, client.getLogFormat(eventHubMessages));
      eventHubMessages = undefined;
      assert.equal(constants.INVALID, client.getLogFormat(eventHubMessages));
    });
  });

  describe('#extractResourceId', function() {
    it('should parse a valid record', function() {
      record = {'resourceId': '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/PROVIDERS/MICROSOFT.COMPUTE/VIRTUALMACHINES/SOME-VM'}
      expectedMetadata = {'tags': ["subscription_id:12345678-1234-abcd-1234-1234567890ab","resource_group:some-resource-group"], 'source': 'azure.compute'}
      assert.deepEqual(expectedMetadata, client.extractResourceId(record))
    });
    it('should parse a valid record without provider', function() {
      record = {'resourceId': '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP'}
      expectedMetadata = {'tags': ["subscription_id:12345678-1234-abcd-1234-1234567890ab","resource_group:some-resource-group"], 'source': ''}
      assert.deepEqual(expectedMetadata, client.extractResourceId(record))
    });
    it('should parse a valid record without provider and resource group', function() {
      record = {'resourceId': '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB'}
      expectedMetadata = {'tags': ["subscription_id:12345678-1234-abcd-1234-1234567890ab"], 'source': ''}
      assert.deepEqual(expectedMetadata, client.extractResourceId(record))
    });
    it('should not fail on record without resourceId', function() {
      record = {'key':'value'}
      expectedMetadata = {'tags': [], 'source': ''}
      assert.deepEqual(expectedMetadata, client.extractResourceId(record))
    });
    it('should not fail on string record', function() {
      record = {'key':'value'}
      expectedMetadata = {'tags': [], 'source': ''}
      assert.deepEqual(expectedMetadata, client.extractResourceId(record))
    });
    it('should not fail on improper resourceId', function() {
      record = {'resourceId': 'foo/bar'}
      expectedMetadata = {'tags': [], 'source': ''}
      assert.deepEqual(expectedMetadata, client.extractResourceId(record))
    });
    it('should not fail with an invalid source', function() {
      record = {'resourceId': '/SUBSCRIPTIONS/12345678-1234-ABCD-1234-1234567890AB/RESOURCEGROUPS/SOME-RESOURCE-GROUP/PROVIDERS/////'}
      expectedMetadata = {'tags': ["subscription_id:12345678-1234-abcd-1234-1234567890ab","resource_group:some-resource-group"], 'source': ''}
      assert.deepEqual(expectedMetadata, client.extractResourceId(record))
    });
  })
});
