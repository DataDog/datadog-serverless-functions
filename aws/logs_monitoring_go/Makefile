BINARY_NAME := bootstrap
VERSION_FILE := cmd/forwarder/main.go
VERSION := $(shell perl -ne 'print $$1 if /var\s+Version\s*=\s*"([^"]+)"/' $(VERSION_FILE))

GOOS := linux
GOARCH := arm64
GOFIPS140 ?= off
GO_BUILD_FLAGS ?= -tags lambda.norpc -ldflags="-s -X main.Version=$(VERSION)" -installsuffix nocgo

.PHONY: build
build:
	GOOS=$(GOOS) GOARCH=$(GOARCH) GOFIPS140=$(GOFIPS140) go build $(GO_BUILD_FLAGS) -o $(BINARY_NAME) ./cmd/forwarder/

GO_TEST_FLAGS ?= -shuffle=on -race

.PHONY: test
test:
	go test $(GO_TEST_FLAGS) ./...

ZIP_PREFIX := aws-dd-forwarder
ZIP_NAME := $(ZIP_PREFIX)-$(VERSION).zip
LICENSE_FILES := LICENSE NOTICE LICENSE-3rdparty.csv LICENSES

.PHONY: package
package: build
	rm -f $(ZIP_NAME)
	zip -r $(ZIP_NAME) $(BINARY_NAME) $(LICENSE_FILES)

.PHONY: clean
clean:
	rm -f $(BINARY_NAME) $(ZIP_NAME) $(ZIP_PREFIX)-*.zip $(ZIP_PREFIX)-*.sha256

.PHONY: lint
lint:
	golangci-lint run ./...

.PHONY: audit
audit:
	go vet ./...
	go tool govulncheck
