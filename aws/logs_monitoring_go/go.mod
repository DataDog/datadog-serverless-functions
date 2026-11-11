module github.com/DataDog/datadog-serverless-functions/aws/logs_monitoring_go

go 1.27

require (
	github.com/aws/aws-lambda-go v1.55.1
	github.com/aws/aws-sdk-go-v2 v1.47.8
	github.com/aws/aws-sdk-go-v2/config v1.33.16
	github.com/aws/aws-sdk-go-v2/service/kms v1.62.5
	github.com/aws/aws-sdk-go-v2/service/lambda v1.114.3
	github.com/aws/aws-sdk-go-v2/service/s3 v1.114.9
	github.com/aws/aws-sdk-go-v2/service/secretsmanager v1.50.11
	github.com/aws/aws-sdk-go-v2/service/sqs v1.52.11
	github.com/aws/aws-sdk-go-v2/service/ssm v1.82.0
	github.com/stretchr/testify v1.12.1
	go.uber.org/mock v0.6.0
	golang.org/x/sync v0.25.0
)

require (
	github.com/aws/aws-sdk-go-v2/aws/protocol/eventstream v1.7.26 // indirect
	github.com/aws/aws-sdk-go-v2/credentials v1.20.16 // indirect
	github.com/aws/aws-sdk-go-v2/feature/ec2/imds v1.20.8 // indirect
	github.com/aws/aws-sdk-go-v2/internal/configsources v1.5.11 // indirect
	github.com/aws/aws-sdk-go-v2/internal/endpoints/v2 v2.8.11 // indirect
	github.com/aws/aws-sdk-go-v2/internal/v4a v1.5.11 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/accept-encoding v1.13.24 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/checksum v1.11.12 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/presigned-url v1.14.11 // indirect
	github.com/aws/aws-sdk-go-v2/service/internal/s3shared v1.20.11 // indirect
	github.com/aws/aws-sdk-go-v2/service/signin v1.12.4 // indirect
	github.com/aws/aws-sdk-go-v2/service/sso v1.39.4 // indirect
	github.com/aws/aws-sdk-go-v2/service/ssooidc v1.44.4 // indirect
	github.com/aws/aws-sdk-go-v2/service/sts v1.51.9 // indirect
	github.com/aws/smithy-go v1.28.8 // indirect
	github.com/google/go-cmp v0.7.0 // indirect
	go.yaml.in/yaml/v3 v3.0.6 // indirect
	golang.org/x/mod v0.34.0 // indirect
	golang.org/x/sys v0.42.0 // indirect
	golang.org/x/telemetry v0.0.0-20260311193753-579e4da9a98c // indirect
	golang.org/x/tools v0.43.0 // indirect
	golang.org/x/tools/go/packages/packagestest v0.1.1-deprecated // indirect
	golang.org/x/vuln v1.1.4 // indirect
)

tool (
	go.uber.org/mock/mockgen
	golang.org/x/tools/cmd/goimports
	golang.org/x/vuln/cmd/govulncheck
)
