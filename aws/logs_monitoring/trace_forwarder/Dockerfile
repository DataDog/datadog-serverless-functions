FROM golang:1.23

# Install dependencies
COPY . /go/src/github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring/trace_forwarder/
WORKDIR /go/src/github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring/trace_forwarder/

ENV GOOS=linux
ENV GOARCH=arm64

# Build the go binary

RUN make
