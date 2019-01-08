#!/bin/bash

SCRIPTPATH=$(cd `dirname $0` && pwd)

if [ $(uname) == "Darwin" ]; then
    datecmd=gdate
    base64cmd=gbase64
    command -v ${datecmd} >/dev/null 2>&1 || { echo >&2 "${datecmd} is required but is not installed. Install with 'brew install coreutils'.  Aborting."; exit 1; }
    command -v ${base64cmd} >/dev/null 2>&1 || { echo >&2 "${base64cmd} is required but is not installed. Install with 'brew install coreutils'.  Aborting."; exit 1; }
else
    datecmd=date
    base64cmd=base64
fi

ts=$(($(${datecmd} +%s%N)/1000000))
iso8601date=$(${datecmd} -u +"%Y-%m-%dT%H:%M:%SZ")

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

tmp_CWLog_msg=${tmp_data/__message__/$tmp_message}
tmp_CWLog_ts=${tmp_CWLog_msg/__timestamp__/$ts}
tmp_CWLog_isodate=${tmp_CWLog_ts/__iso8601date__/$iso8601date}
tmp_CWLogB64=$(echo $tmp_CWLog_isodate | gzip | ${base64cmd} -w0)

printf "${tmp_CWLogEvent/__b64data__/$tmp_CWLogB64}"
