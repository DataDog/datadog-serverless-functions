''' FIXME: Documentation on what this function does, and how to configure it
'''

import json
from base64 import b64decode

import boto3

from datadog import initialize, ThreadStats

# retrieve datadog options from KMS
KMS_ENCRYPTED_KEYS = "<kmsEncryptedToken>"  # Enter the base-64 encoded, encrypted Datadog token (CiphertextBlob)
kms = boto3.client('kms')
datadog_keys = kms.decrypt(CiphertextBlob=b64decode(KMS_ENCRYPTED_KEYS))['Plaintext']
initialize(**json.loads(datadog_keys))

stats = ThreadStats()
stats.start(flush_in_thread=False)

print 'Lambda function initialized, ready to send metrics'


def send_metric(event, context):
    """
    """
    print event
    print context
    stats.gauge('dd.aws.lambda.test', 1)
    stats.flush()
    return {'Status': 'OK'}
