.PHONY: build package test lint clean sam-build sam-invoke sam-deploy build-ForwarderFunction

BINARY_NAME := bootstrap
ZIP_NAME := forwarder.zip

build:
	GOOS=linux GOARCH=arm64 go build -o $(BINARY_NAME) ./cmd/forwarder/

# Used by `sam build`
build-ForwarderFunction:
	GOOS=linux GOARCH=arm64 go build -o $(ARTIFACTS_DIR)/bootstrap ./cmd/forwarder/

package: build
	zip $(ZIP_NAME) $(BINARY_NAME)

test:
	go test -race ./...

lint:
	golangci-lint run ./...

clean:
	rm -f $(BINARY_NAME) $(ZIP_NAME)

sam-build:
	sam build

EVENT ?= events/cloudwatch_logs.json
sam-invoke: sam-build
	sam local invoke ForwarderFunction -e $(EVENT)

sam-deploy: sam-build
	sam deploy
