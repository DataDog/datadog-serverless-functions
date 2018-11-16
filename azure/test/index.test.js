var assert = require('assert');
var azure = require('../activity_logs_monitoring');

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
    it('should return default json', function() {
      eventHubMessages = [{'records': [{}, {}]}, {'records': [{}, {}]}];
      assert.equal(azure.DEFAULT_JSON, azure.getEventHubMessagesFormat(eventHubMessages));
    });
    it('should return raw json', function() {
      eventHubMessages = {'key': 'value', 'otherkey':'othervalue'};
      assert.equal(azure.RAW_JSON, azure.getEventHubMessagesFormat(eventHubMessages));
    });
    it('should return json no records', function() {
      eventHubMessages = [{'key': 'value', 'otherkey':'othervalue'}, {'key': 'value', 'otherkey':'othervalue'}];
      assert.equal(azure.JSON_NO_RECORDS, azure.getEventHubMessagesFormat(eventHubMessages));
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
});
