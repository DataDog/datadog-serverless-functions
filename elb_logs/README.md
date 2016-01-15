# sample

ELB Log event example
```json
{
    "Records": [{
        "eventVersion": "2.0",
        "eventTime": "2016-01-14T23:04:27.215Z",
        "requestParameters": {
            "sourceIPAddress": "54.225.183.223"
        },
        "s3": {
            "configurationId": "3e6e23b6-3cc2-4d80-94be-a202649f3c4e",
            "object": {
                "eTag": "b920c39d84c99220c7f3ef6bfcce1dd2-3",
                "sequencer": "0056982978730E2BA3",
                "key": "AWSLogs/727006795293/elasticloadbalancing/us-east-1/2016/01/14/727006795293_elasticloadbalancing_us-east-1_app-datad0g-com-cert_20160114T2300Z_54.225.183.223_5ypsvibo.log",
                "size": 13014151
            },
            "bucket": {
                "arn": "arn:aws:s3:::dd-elb-logs-staging",
                "name": "dd-elb-logs-staging",
                "ownerIdentity": {
                    "principalId": "A12XJCAT0M63SB"
                }
            },
            "s3SchemaVersion": "1.0"
        },
        "responseElements": {
            "x-amz-id-2": "wTRfuqzipOwfeBA0lOJIAYqXgh5wRlQLXuRuaJhKy48TCeJ3ECOh9HxaBm/IHoATEuX0XXRrcjQ=",
            "x-amz-request-id": "5AAAF9097E2F143A"
        },
        "awsRegion": "us-east-1",
        "eventName": "ObjectCreated:CompleteMultipartUpload",
        "userIdentity": {
            "principalId": "AWS:AIDAITAATZTOMD5FZTPKC"
        },
        "eventSource": "aws:s3"
    }]
}
```

[Sample log line](http://docs.aws.amazon.com/ElasticLoadBalancing/latest/DeveloperGuide/access-log-collection.html)
