# vpc_flow_log_monitoring
Process a VPC Flow Log monitoring DATA_MESSAGE, coming from CLOUDWATCH LOGS

# VPC Flow Log message example
```
2 123456789010 eni-abc123de 172.31.16.139 172.31.16.21 20641 22 6 20 4249 1418530010 1418530070 ACCEPT OK
```

which correspond to the following fields:
```
version, account, eni, source, destination, srcport, destport="22", protocol="6", packets, bytes, windowstart, windowend, action="REJECT", flowlogstatus
```
