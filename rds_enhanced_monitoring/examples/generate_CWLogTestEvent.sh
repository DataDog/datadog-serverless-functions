#!/bin/bash

SCRIPTPATH=$(cd `dirname $0` && pwd)

ts=$(date +%s)000
tmp_CWLogEvent='''
{ "awslogs": {
	"data":"__b64data__"
	}
}
'''

tmp_message=$(sed -e 's/"/\\"/g' $SCRIPTPATH/tmp_message.json)
tmp_CWLog=$(cat $SCRIPTPATH/tmp_CWLog.json)

tmp_CWLogMessage=${tmp_CWLog/__message__/$tmp_message}
b64_CWLogMessage=$(echo ${tmp_CWLogMessage/__timestamp__/$ts} | gzip | base64 -w0)

printf "${tmp_CWLogEvent/__b64data__/$b64_CWLogMessage}"