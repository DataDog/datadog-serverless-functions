### Datadog Forwarder for Alibaba Cloud Log Service logs [experimental]

Alibaba Function Compute Service Function to ship logs from an Alibaba Log Service Logstore to Datadog.

#### Setup

1. Please ensure the configuration of the Log service has the appropriate System Policy roles, specifically `AliyunLogFullAccess` and `AliyunLogReadOnlyAccess`, specified [here](https://www.alibabacloud.com/help/doc-detail/84091.htm?spm=a2c63.p38356.b99.73.6371ae6e3h6tYZ).

2. In the same region as Log Service project, create a Function Compute Service, function and trigger.

  * Follow steps 1-3 [here](https://www.alibabacloud.com/help/doc-detail/60291.htm?spm=a2c63.p38356.879954.7.ec312052WIGHNC).
  * 3.1, choose "Blank Template". Then on the Functions Guide Page, select the "Code" Tab and copy/paste in the details of [index.py](index.py). Please be sure to replace variables in Lines 24-27 with your own values.
  * 3.2, Complete the required items to configure the trigger, specifically the trigger name, the Log Service project name, and the Logstore name. For Invocation Interval and Retry should be configured appropriately for your environment. Please note that Retries could duplicate log entries.
  * 3.3, Set Function Handler: `index.handler` , Runtime: `python2.7` , as seen [here](https://cl.ly/639758a37d1d).
  * 3.4, Ensure appropriate roles `AliyunLogFullAccess` and `AliyunLogReadOnlyAccess` are set.

##### Notes

This is an experimental feature.