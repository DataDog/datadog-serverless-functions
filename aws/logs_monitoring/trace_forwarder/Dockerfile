FROM golang:1.12
ARG runtime

RUN go get -u github.com/golang/dep/cmd/dep

# Install dependencies
COPY . /go/src/github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring/trace_forwarder/
WORKDIR /go/src/github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring/trace_forwarder/
ENV GOOS=linux
ENV GOARCH=amd64
RUN dep ensure

# Build the go binary

RUN make
