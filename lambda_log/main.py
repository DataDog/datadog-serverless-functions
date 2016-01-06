import re
import gzip
import json
from StringIO import StringIO

from datadog import initialize, ThreadStats

initialize(**options)

stats = ThreadStats()
stats.start(flush_in_thread=False)

DURATION_RE = '\\tDuration: ([0-9.]+) ms'
BILLED_DURATION_RE = '\\tBilled Duration: ([0-9.]+) ms'
MEMORY_SIZE = '\\tMemory Size: ([0-9.]+) MB'
MAX_MEMORY_USED = '\\tMax Memory Used: ([0-9.]+) MB'


def send_metric(event, context):
    """
    """
    # event is a dict containing a base64 string gzipped
    event = event['awslogs']['data']
    event = json.loads(
        gzip.GzipFile(fileobj=StringIO(event.decode('base64'))).read()
    )
    tags = [
        'account:%s' % event['owner'],
        'function_name:%s' % context.function_name,
        'function_version:%s' % context.function_version,
    ]
    for log_event in event['logEvents']:
        if log_event['message'].startswith('REPORT'):
            message = log_event['message']
            ts = log_event['timestamp'] / 1000
            duration = float(re.search(DURATION_RE, message).groups()[0])
            billed_duration = float(re.search(DURATION_RE, message).groups()[0])
            memory_size = float(re.search(MEMORY_SIZE, message).groups()[0])
            max_memory_used = float(re.search(MAX_MEMORY_USED, message).groups()[0])
            stats.histogram(
                'dd.aws.lambda.duration', duration, timestamp=ts, tags=tags
            )
            stats.histogram(
                'dd.aws.lambda.billed_duration', billed_duration,
                timestamp=ts, tags=tags
            )
            stats.histogram(
                'dd.aws.lambda.memory_size', memory_size,
                timestamp=ts, tags=tags
            )
            stats.histogram(
                'dd.aws.lambda.max_memory_used', max_memory_used,
                timestamp=ts, tags=tags
            )
    stats.flush()
    return {'Status': 'OK'}
