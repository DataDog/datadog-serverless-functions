#!/bin/bash

SCRIPTPATH=$(cd `dirname $0` && pwd)

ts=$(($(date +%s%N)/100000))
tmp_CWLogEvent='''
{
  "awslogs": {
    "data":"__b64data__"
  }
}
'''

tmp_data='''
{
  "logStream": "db-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "messageType": "DATA_MESSAGE",
  "logEvents": [
    {
      "timestamp": __timestamp__,
      "message": "__message__"
    }
  ],
  "owner": "123456789000",
  "subscriptionFilters": [
    "dd-rdsenhanced-filter"
  ],
  "logGroup": "RDSOSMetrics"
}
'''

tmp_message=$(sed -e 's/"/\\"/g' $SCRIPTPATH/tmp_message.json)

tmp_CWLogRaw=${tmp_data/__message__/$tmp_message}
tmp_CWLogB64=$(echo ${tmp_CWLogRaw/__timestamp__/$ts} | gzip | base64 -w0)

printf "${tmp_CWLogEvent/__b64data__/$tmp_CWLogB64}"