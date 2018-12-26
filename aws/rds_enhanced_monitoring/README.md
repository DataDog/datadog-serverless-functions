# rds_enhanced_monitoring
Process a RDS enhanced monitoring DATA_MESSAGE, coming from CLOUDWATCH LOGS

# RDS message example
```json
    {
        "engine": "Aurora",
        "instanceID": "instanceid",
        "instanceResourceID": "db-QPCTQVLJ4WIQPCTQVLJ4WIJ4WI",
        "timestamp": "2016-01-01T01:01:01Z",
        "version": 1.00,
        "uptime": "10 days, 1:53:04",
        "numVCPUs": 2,
        "cpuUtilization": {
            "guest": 0.00,
            "irq": 0.00,
            "system": 0.88,
            "wait": 0.54,
            "idle": 97.57,
            "user": 0.68,
            "total": 1.56,
            "steal": 0.07,
            "nice": 0.25
        },
        "loadAverageMinute": {
            "fifteen": 0.14,
            "five": 0.17,
            "one": 0.18
        },
        "memory": {
            "writeback": 0,
            "hugePagesFree": 0,
            "hugePagesRsvd": 0,
            "hugePagesSurp": 0,
            "cached": 11742648,
            "hugePagesSize": 2048,
            "free": 259016,
            "hugePagesTotal": 0,
            "inactive": 1817176,
            "pageTables": 25808,
            "dirty": 660,
            "mapped": 8087612,
            "active": 13016084,
            "total": 15670012,
            "slab": 437916,
            "buffers": 272136
        },
        "tasks": {
            "sleeping": 223,
            "zombie": 0,
            "running": 1,
            "stopped": 0,
            "total": 224,
            "blocked": 0
        },
        "swap": {
            "cached": 0,
            "total": 0,
            "free": 0
        },
        "network": [{
            "interface": "eth0",
            "rx": 217.57,
            "tx": 2319.67
        }],
        "diskIO": [{
            "readLatency": 0.00,
            "writeLatency": 1.53,
            "writeThroughput": 2048.20,
            "readThroughput": 0.00,
            "readIOsPS": 0.00,
            "diskQueueDepth": 0,
            "writeIOsPS": 5.83
        }],
        "fileSys": [{
            "used": 7006720,
            "name": "rdsfilesys",
            "usedFiles": 2650,
            "usedFilePercent": 0.13,
            "maxFiles": 1966080,
            "mountPoint": "/rdsdbdata",
            "total": 30828540,
            "usedPercent": 22.73
        }],
        "processList": [{
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.00,
            "id": 8455,
            "rss": 10487696
        }, {
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.82,
            "id": 8782,
            "rss": 10487696
        }, {
            "vss": 11170084,
            "name": "aurora",
            "tgid": 8455,
            "parentID": 1,
            "memoryUsedPc": 66.93,
            "cpuUsedPc": 0.05,
            "id": 8784,
            "rss": 10487696
        }, {
            "vss": 647304,
            "name": "OS processes",
            "tgid": 0,
            "parentID": 0,
            "memoryUsedPc": 0.18,
            "cpuUsedPc": 0.02,
            "id": 0,
            "rss": 22600
        }, {
            "vss": 3244792,
            "name": "RDS processes",
            "tgid": 0,
            "parentID": 0,
            "memoryUsedPc": 2.80,
            "cpuUsedPc": 0.78,
            "id": 0,
            "rss": 441652
        }]
    }
```
