BINARY_NAME := bootstrap
ZIP_NAME := forwarder.zip

# Go
.PHONY: build package test lint clean audit

build:
	GOOS=linux GOARCH=arm64 go build -o $(BINARY_NAME) ./cmd/forwarder/

package: build
	zip $(ZIP_NAME) $(BINARY_NAME)

test:
	go test -race ./...

lint:
	golangci-lint run ./...

audit:
	go vet ./...
	go tool staticcheck ./...
	go tool govulncheck

clean:
	rm -f $(BINARY_NAME) $(ZIP_NAME)

# SAM
.PHONY: build-ForwarderFunction sam-build sam-invoke sam-deploy 

build-ForwarderFunction:
	GOOS=linux GOARCH=arm64 go build -o $(ARTIFACTS_DIR)/bootstrap ./cmd/forwarder/

sam-build:
	sam build

sam-deploy: sam-build
	sam deploy

EVENT ?= events/cloudwatch_logs.json
sam-invoke: sam-build
	sam local invoke ForwarderFunction -e $(EVENT)
