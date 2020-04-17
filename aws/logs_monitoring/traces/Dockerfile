FROM golang:1.12
ARG runtime

RUN go get -u github.com/golang/dep/cmd/dep

# Install dependencies
COPY . /go/src/github.com/DataDog/datadog-trace-forwarder
WORKDIR /go/src/github.com/DataDog/datadog-trace-forwarder
ENV GOOS=linux
ENV GOARCH=amd64
RUN dep ensure

# Build the go binary

RUN make

RUN mkdir -p /python/lib/$runtime/site-packages
RUN cp -r bin trace_forwarder/
RUN cp -r trace_forwarder /python/lib/$runtime/site-packages
