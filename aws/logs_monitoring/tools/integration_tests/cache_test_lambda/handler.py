import json


def handle(event, context):
    print(json.dumps(event))

    return {"statusCode": 200}
