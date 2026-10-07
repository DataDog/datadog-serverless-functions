BINARY_NAME := bootstrap
FORWARDER_VERSION := $(shell perl -ne 'print $$1 if /ForwarderVersion\s*=\s*"([^"]+)"/' internal/config/config.go)
ZIP_NAME := aws-dd-forwarder-$(FORWARDER_VERSION).zip

# Go

.PHONY: build
build:
	GOOS=linux GOARCH=arm64 go build -tags lambda.norpc -ldflags="-s" -installsuffix nocgo -o $(BINARY_NAME) ./cmd/forwarder/

.PHONY: package
package: build
	rm -f $(ZIP_NAME)
	zip $(ZIP_NAME) $(BINARY_NAME)

.PHONY: test
test:
	go test -shuffle=on -race ./...

.PHONY: lint
lint:
	golangci-lint run ./...

.PHONY: audit
audit:
	go vet ./...
	go tool govulncheck

.PHONY: generate
generate:
	go generate ./...

.PHONY: clean
clean:
	rm -f $(BINARY_NAME) $(ZIP_NAME) aws-dd-forwarder-*.zip

# SAM

# Used only by SAM
.PHONY: build-ForwarderFunction
build-ForwarderFunction:
	GOOS=linux GOARCH=arm64 go build -tags lambda.norpc -ldflags="-s" -installsuffix nocgo -o $(ARTIFACTS_DIR)/bootstrap ./cmd/forwarder/

.PHONY: sam-build
sam-build:
	sam build

.PHONY: sam-deploy
sam-deploy: sam-build
	sam deploy

EVENT ?= events/cloudwatch_logs.json

.PHONY: sam-invoke
sam-invoke: sam-build
	sam local invoke ForwarderFunction -e $(EVENT)
