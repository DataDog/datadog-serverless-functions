# Datadog Trace Forwarder

Shared libary for submitting traces to trace intake. 
Features include:
 * Tools for building AWS Lambda Layer from library
 * Trace obfuscation, (using logic from datadog-agent)
 * Submits Stats/Transcations for traces
 * Python bindings

```python
from trace_forwarder.connection import TraceConnection
conn = TraceConnection("datadoghq.com", "my_api_key")
conn.send("""
{
  "traces": [
    [
      {
        "trace_id": "75BCD15",
        "span_id": "248B0C57D64F053",
        "parent_id": "B853ABB94CFE745C",
        "name": "aws.lambda",
        "type": "web",
        "resource": "aws.lambda",
        "error": 0,
        "meta": {
          "language": "javascript",
          "http.url": "https://www.google.com?api_key=12AB45DEWF"
        },
        "metrics": {
          "_sample_rate": 1,
          "_sampling_priority_v1": 2
        },
        "start": 1565381107070475300,
        "duration": 539684570,
        "service": "node"
      }
    ]
  ]
}
""")
```

## Requirements

* dep
* go 1.12 or higher
* docker

## Building Go Binary

```bash
dep ensure
make
```

Output is saved to bin, and the shared library will be compatible with your local environment. If you want to build a linux compatible binary, you will need to use docker, (setting GOOS/GOARCH enviornment variable doesn't work for shared libraries).

```bash
./scripts/build_linux_go_bin.sh
```

## Lambda Layer
### Building Lambda Layer

You can build the lambda layer with the following command

```bash
./scripts/build_layers.sh
```

### Publishing to staging

```bash
./scripts/publish_staging.sh
```

### Publishing to prod

```bash
./scripts/publish_prod.sh
```