import json


def ironmaiden(event, context):
    print(json.dumps(event))

    return {"statusCode": 200}


def megadeth(event, context):
    print(json.dumps(event))

    return {"statusCode": 200}
