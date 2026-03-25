BINARY_NAME := bootstrap
ZIP_NAME := forwarder.zip

# Go

.PHONY: build
build:
	GOOS=linux GOARCH=arm64 go build -ldflags="-s" -installsuffix nocgo -o $(BINARY_NAME) ./cmd/forwarder/

.PHONY: package
package: build
	zip $(ZIP_NAME) $(BINARY_NAME)

.PHONY: test
test:
	go test -race ./...

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
	rm -f $(BINARY_NAME) $(ZIP_NAME)

# SAM

# Used only by SAM
.PHONY: build-ForwarderFunction
build-ForwarderFunction:
	GOOS=linux GOARCH=arm64 go build -ldflags="-s" -installsuffix nocgo -o $(ARTIFACTS_DIR)/bootstrap ./cmd/forwarder/

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
