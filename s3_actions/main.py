from datadog import initialize, api

initialize(**options)

api.Metric.send(
    metric='dd.tristan.lambda.initialized', type='counter', points=1,
    tags=['function:s3_actions']
)
print 'initialized the lambda function, ready to send metrics'


def send_metric(event, context):
    """
    """
    for record in event['Records']:
        print record
        source = record['eventSource'].replace(':', '_')
        name = record['eventName']
        region = record['awsRegion']

        bucket = record['s3']['bucket']['name']
        folder = (record['s3']['object']['key'] or '/').split('/', 1)[0]

        output = api.Metric.send(
            metric='dd.tristan.lambda.occurences',
            type='counter',
            points=1,
            tags=[
                'source:%s' % source, 'name:%s' % name,
                'region:%s' % region, 'bucket:%s' % bucket,
                'folder:%s' % folder, 'host:'
            ]
        )
    return output
