FROM golang:1.22
WORKDIR /go/src/github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring/trace_forwarder/
COPY go.mod .
RUN go mod download
COPY . .
RUN make
