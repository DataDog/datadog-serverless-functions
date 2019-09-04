NAME := datadog-log-forwarder
RESOURCE_NAME := DatadogLogForwarder
MODULE_NAME := datadog_log_forwarder
S3_BUCKET := bookbub-sam-lambda-functions

ROLLBAR_ACCESS_TOKEN_PATH := /rollbar/project_access_tokens/${NAME}
DATADOG_API_KEY_PATH := /datadog/api_access_key

check-env:
	$(if ${ENVIRONMENT},,$(error You must set ENVIRONMENT))

# DEVELOPMENT

build:
		sam build --use-container

dev: build
		sam local invoke \
			--env-vars env-vars.json \
			--event event.json \
			--parameter-overrides 'ParameterKey=Environment,ParameterValue=development' \
			$(RESOURCE_NAME)

# TEST

test:
	docker build --build-arg NAME=$(MODULE_NAME) -t $(NAME):latest -f Dockerfile.test .
	docker run --rm -e ENVIRONMENT=test -it $(NAME):latest pytest

# DEPLOY

validate:
	sam validate --template template.yaml

package: check-env
	aws s3 mb s3://${S3_BUCKET}
	sam package \
		--s3-bucket ${S3_BUCKET} \
		--s3-prefix ${ENVIRONMENT}-${NAME} \
		--template-file .aws-sam/build/template.yaml \
		--output-template-file .packaged-${ENVIRONMENT}.yaml

deploy: check-env validate build package
	sam deploy \
		--template-file .packaged-${ENVIRONMENT}.yaml \
		--stack-name ${ENVIRONMENT}-$(NAME) \
		--capabilities CAPABILITY_IAM \
		--parameter-overrides \
			'Environment=${ENVIRONMENT}' \
			'RollbarAccessToken=$(ROLLBAR_ACCESS_TOKEN_PATH)' \
                        'DatadogApiKey=$(DATADOG_API_KEY_PATH)'

