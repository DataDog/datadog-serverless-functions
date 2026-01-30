#!/usr/bin/env bash

set -o nounset -o pipefail -o errexit

log_info() {
    local BLUE='\033[0;34m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${BLUE}" "${*}" "${RESET}" 1>&2
}

log_success() {
    local GREEN='\033[0;32m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${GREEN}" "${*}" "${RESET}" 1>&2
}

log_error() {
    local RED='\033[0;31m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${RED}" "${*}" "${RESET}" 1>&2
    exit 1
}

user_read_input() {
    if [[ ${#} -lt 2 ]]; then
        var_red "Usage: var_read_input VAR_PROMPT VAR_NAME"
        return 1
    fi

    local VAR_PROMPT="${1}"
    shift

    local VAR_NAME="${1}"
    shift

    if [[ -n ${BASH_VERSION} ]]; then
        read -r -p "${VAR_PROMPT}" "${@}" "${VAR_NAME}" </dev/tty
    elif [[ -n ${ZSH_VERSION} ]]; then
        read -r "${VAR_NAME}?${VAR_PROMPT}" "${@}" </dev/tty
    else
        var_error "Shell not supported for reading user input"
        return 1
    fi
}

user_confirm() {
    local DEFAULT_PROMPT="[y/N]"
    local DEFAULT_RETURN=1

    if [[ ${2:-} == "true" ]] || [[ ${2:-} == "0" ]]; then
        DEFAULT_RETURN=0
        DEFAULT_PROMPT="[Y/n]"
    fi

    local input
    user_read_input "${1:-Are you sure}? ${DEFAULT_PROMPT} " input

    case "${input}" in
    [yY][eE][sS] | [yY])
        return 0
        ;;

    [nN][oO] | [nN])
        return 1
        ;;

    *)
        return ${DEFAULT_RETURN}
        ;;
    esac
}

if [[ ${#} -ne 2 ]]; then
    log_error "Usage: ${0} DESIRED_VERSION ACCOUNT[sandbox|prod|datadog]"
fi

if ! command -v jq >/dev/null 2>&1; then
    log_error "jq not found, please install it following instructions here https://github.com/jqlang/jq#installation"
fi

if ! command -v yq >/dev/null 2>&1; then
    log_error "yq not found, please install it following instructions here https://github.com/mikefarah/yq#install"
fi

if ! command -v gh >/dev/null 2>&1; then
    log_error "gh not found, please install it following instructions here https://github.com/cli/cli?tab=readme-ov-file#installation"
fi

# Before we start the release, ensure that Docker or container is running
if docker info > /dev/null 2>&1; then
    log_info "Using Docker for container operations"
elif container system status > /dev/null 2>&1; then
    log_info "Using Apple container for container operations"
else
    log_error "Neither Docker nor container is running. Please start Docker or run 'container system start'"
fi

# Read the desired version
if [[ ! ${1} =~ [0-9]+\.[0-9]+\.[0-9]+ ]]; then
    log_error "You must use a semantic version (e.g. 3.1.4)"
else
    FORWARDER_VERSION="${1}"
fi

# Check account parameter
VALID_ACCOUNTS=("sandbox" "prod" "datadog")
if [[ ! ${VALID_ACCOUNTS[@]} =~ ${2} ]]; then
    log_error "The account parameter was invalid. Please choose sandbox, prod, or datadog"
fi
ACCOUNT="${2}"

if [[ ${ACCOUNT} == "prod" ]]; then
    BUCKET="datadog-cloudformation-template"
elif [[ ${ACCOUNT} == "datadog" ]]; then
    BUCKET="datadog-forwarder-cloudformation-template-org-2"
elif [[ ${ACCOUNT} == "sandbox" ]]; then
    if [[ ${DEPLOY_TO_SERVERLESS_SANDBOX:-} == "true" ]]; then
        BUCKET="datadog-cloudformation-template-serverless-sandbox"
    else
        BUCKET="datadog-cloudformation-template-test-sandbox"
    fi
fi

# Read the current version
CURRENT_VERSION=$(yq '.Mappings.Constants.DdForwarder.Version' "template.yaml")

LAYER_NAME="Datadog-Forwarder"
BUNDLE_PATH=".forwarder/aws-dd-forwarder-${FORWARDER_VERSION}.zip"
VERSIONS_JSON_PATH=".forwarder/versions.json"
VERSIONS_BUCKET="datadog-opensource-asset-versions"

aws_login() {
    cfg=("$@")
    shift

    if [[ ${ACCOUNT} == "prod" ]]; then
        aws-vault exec sso-prod-lambda-admin -- ${cfg[@]}
    elif [[ ${ACCOUNT} == "datadog" ]]; then
        aws-vault exec sso-prod-lambda-admin -- ${cfg[@]}
    else
        if [[ ${DEPLOY_TO_SERVERLESS_SANDBOX:-} == "true" ]]; then
            aws-vault exec sso-serverless-sandbox-account-admin -- ${cfg[@]}
        else
            aws-vault exec sso-sandbox-account-admin -- ${cfg[@]}
        fi
    fi
}

get_max_layer_version() {
    last_layer_version=$(aws_login aws lambda list-layer-versions --layer-name "${LAYER_NAME}" --region us-west-2 | jq -r ".LayerVersions | .[0] |  .Version")
    if [ "$last_layer_version" == "null" ]; then
        echo 0
    else
        echo "${last_layer_version}"
    fi
}

generate_versions_json() {
    log_info "Generating versions.json from GitHub release data..."

    local releases_json
    releases_json=$(gh release list --repo DataDog/datadog-serverless-functions --limit 200 --json tagName,name,publishedAt)

    local versions_json
    versions_json=$(echo "${releases_json}" | jq -r '
        [
            .[] |
            select(.tagName | startswith("aws-dd-forwarder-")) |

            # Extract forwarder version from tag (e.g., aws-dd-forwarder-5.1.0 -> 5.1.0)
            (.tagName | capture("aws-dd-forwarder-(?<version>[0-9]+\\.[0-9]+\\.[0-9]+)")) as $forwarder |

            # Extract layer version from name (e.g., "aws-dd-forwarder-5.1.0 (Layer v92)" -> 92)
            (.name | capture("\\(Layer v(?<layer>[0-9]+)\\)")) as $layer |

            # Only include if both extractions succeeded
            select($forwarder != null and $layer != null) |

            {
                layer_version: $layer.layer,
                forwarder_version: $forwarder.version,
                release_date: (.publishedAt | split("T")[0]),
                published_at: .publishedAt
            }
        ] |

        # Group by layer_version and keep only the most recent forwarder version for each layer
        group_by(.layer_version) |
        map({
            layer_version: .[0].layer_version,
            forwarder_version: (sort_by(.published_at) | reverse | .[0].forwarder_version),
            release_date: (sort_by(.published_at) | reverse | .[0].release_date)
        }) |

        sort_by(.layer_version | tonumber) | reverse |

        {
            latest: {
                layer_version: .[0].layer_version,
                forwarder_version: .[0].forwarder_version,
                release_date: .[0].release_date
            },
            mappings: (
                reduce .[] as $item (
                    {};
                    . + {($item.layer_version): $item.forwarder_version}
                )
            )
        }
    ')

    echo "${versions_json}" > "${VERSIONS_JSON_PATH}"
    log_success "Generated ${VERSIONS_JSON_PATH}"
}

upload_versions_json() {
    log_info "Uploading versions.json to s3://${VERSIONS_BUCKET}/forwarder/versions.json..."

    aws_login aws s3 cp "${VERSIONS_JSON_PATH}" "s3://${VERSIONS_BUCKET}/forwarder/versions.json"

    log_success "Uploaded versions.json to S3!"
}

datadog_release() {
    if ! user_confirm "Did you update the DdForwarder version and Layer in the template.yaml file before releasing"; then
        log_error "Please update the Forwarder version in the template.yaml file"
    fi

    if [[ ! -e ${BUNDLE_PATH} ]] || ! user_confirm "Bundle already exists. Do you want to use it" "true"; then
        log_info "Building the Forwarder bundle..."
        ./tools/build_bundle.sh "${FORWARDER_VERSION}"
    fi

    # Upload the bundle to S3 instead of GitHub for a org 2 release
    log_info "Uploading a non-public version of Forwarder to S3..."
    aws_login aws s3 cp "${BUNDLE_PATH}" "s3://${BUCKET}/aws/forwarder-zip/aws-dd-forwarder-${FORWARDER_VERSION}.zip"

    # set urls
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder/${FORWARDER_VERSION}.yaml"
    FORWARDER_SOURCE_URL="s3://${BUCKET}/aws/forwarder-zip/aws-dd-forwarder-${FORWARDER_VERSION}.zip"

    # don't publish layers we'll use the zip copier instead
}

sandbox_release() {
    if [[ ! -e ${BUNDLE_PATH} ]] || ! user_confirm "Bundle already exists. Do you want to use it" "true"; then
        log_info "Building the Forwarder bundle..."
        ./tools/build_bundle.sh "${FORWARDER_VERSION}"

        log_info "Signing the Forwarder bundle..."
        aws_login "./tools/sign_bundle.sh" "${BUNDLE_PATH}" "${ACCOUNT}"
    fi

    # Upload the bundle to S3 instead of GitHub for a sandbox release
    log_info "Uploading non-public sandbox version of Forwarder to S3..."
    aws_login aws s3 cp "${BUNDLE_PATH}" "s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${FORWARDER_VERSION}.zip"

    # Upload the sandbox layers
    log_info "Uploading layers"
    ./tools/publish_sandbox.sh "${LAYER_VERSION}" "${FORWARDER_VERSION}"

    # Set vars for use in the installation test
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder-staging/latest.yaml"
    FORWARDER_SOURCE_URL="s3://${BUCKET}/aws/forwarder-staging-zip/aws-dd-forwarder-${FORWARDER_VERSION}.zip"
}

prod_release() {
    if [[ ! $(./tools/semver.sh "${FORWARDER_VERSION}" "${CURRENT_VERSION}") > 0 ]]; then
        log_error "Must use a version greater than the current ($CURRENT_VERSION)"
    fi

    # Make sure we are on the master branch
    if [[ $(git rev-parse --abbrev-ref HEAD) != "master" ]]; then
        log_error "Not on the master branch, aborting."
    fi

    log_info "You are about to\n\t- bump the version from ${CURRENT_VERSION} to ${FORWARDER_VERSION}\n\t- create lambda layer version ${LAYER_VERSION}\n\t- create a release of aws-dd-forwarder-${FORWARDER_VERSION} on GitHub\n\t- upload the template.yaml to s3://${BUCKET}/aws/forwarder/${FORWARDER_VERSION}.yaml\n"

    # Confirm to proceed
    if ! user_confirm "Continue"; then
        log_error "Aborting..."
    fi

    # Get the latest code
    git checkout master
    git pull origin master

    log_info "Bumping the version number to ${FORWARDER_VERSION}..."
    perl -pi -e "s/DD_FORWARDER_VERSION = \"[0-9\.]+/DD_FORWARDER_VERSION = \"${FORWARDER_VERSION}/g" "settings.py"

    # Update template.yaml
    yq --inplace ".Mappings.Constants.DdForwarder.Version |= \"${FORWARDER_VERSION}\"" "template.yaml"
    yq --inplace ".Mappings.Constants.DdForwarder.LayerVersion |= \"${LAYER_VERSION}\"" "template.yaml"

    if ! git diff --quiet; then
        BRANCH_NAME="layer_${LAYER_VERSION}"

        log_info "Opening pull-request version number change on branch ${BRANCH_NAME}..."
        git checkout -b "${BRANCH_NAME}"

        git add "settings.py" "template.yaml"
        git commit --signoff --message "ci(release): Update version from ${CURRENT_VERSION} to ${FORWARDER_VERSION}"
        git push origin "${BRANCH_NAME}"

        gh pr create --base master --head "${BRANCH_NAME}" \
            --title "Update version from ${CURRENT_VERSION} to ${FORWARDER_VERSION}" \
            --body "This PR updates the AWS Forwarder version to ${FORWARDER_VERSION} and the layer version to ${LAYER_VERSION}."

        if ! user_confirm "Review and merge the pull-request before continuing. Continue"; then
            log_error "Aborting... To restart, run the script with PROD_GITHUB_RESTART=true env variable."
        fi
    fi

    prod_asset_push
}

prod_asset_push() {
    git checkout master
    git pull origin master

    GIT_COMMIT="$(git rev-parse HEAD)"
    log_info "Using ${GIT_COMMIT} commit as the release target..."

    if [[ ! -e ${BUNDLE_PATH} ]] || ! user_confirm "Bundle already exists. Do you want to use it" "true"; then
        log_info "Building the Forwarder bundle..."
        ./tools/build_bundle.sh "${FORWARDER_VERSION}"

        log_info "Signing the Forwarder bundle..."
        aws_login ./tools/sign_bundle.sh "${BUNDLE_PATH}" "${ACCOUNT}"
    fi

    log_info "Uploading layers..."
    ./tools/publish_prod.sh "${LAYER_VERSION}" "${FORWARDER_VERSION}"

    # Create a GitHub release
    log_info "Releasing aws-dd-forwarder-${FORWARDER_VERSION}, targetting commit ${GIT_COMMIT}, to GitHub..."

    gh release create "aws-dd-forwarder-${FORWARDER_VERSION}" "${BUNDLE_PATH}#aws-dd-forwarder-${FORWARDER_VERSION}.zip" \
        --title "aws-dd-forwarder-${FORWARDER_VERSION} (Layer v${LAYER_VERSION})" \
        --target "${GIT_COMMIT}" \
        --generate-notes

    # Set vars for use in the installation test
    TEMPLATE_URL="https://${BUCKET}.s3.amazonaws.com/aws/forwarder/latest.yaml"
    FORWARDER_SOURCE_URL="https://github.com/DataDog/datadog-serverless-functions/releases/download/aws-dd-forwarder-${FORWARDER_VERSION}/aws-dd-forwarder-${FORWARDER_VERSION}.zip'"
}

# Validate identity
aws_login aws sts get-caller-identity

CURRENT_ACCOUNT="$(aws_login aws sts get-caller-identity --query Account --output text)"
CURRENT_LAYER_VERSION=$(get_max_layer_version)
LAYER_VERSION=$((CURRENT_LAYER_VERSION + 1))

if [[ ${ACCOUNT} != "datadog" ]]; then
    log_info "Current layer version is ${CURRENT_LAYER_VERSION}, next layer version will be ${LAYER_VERSION}"
fi

log_info "Validating template.yaml..."
aws_login aws cloudformation validate-template --template-body "file://template.yaml"

if [[ ${ACCOUNT} == "prod" ]]; then
    if [[ ${PROD_GITHUB_RESTART:-} == "true" ]]; then
        prod_asset_push
    else
        prod_release
    fi
elif [[ ${ACCOUNT} == "datadog" ]]; then
    datadog_release
else
    sandbox_release
fi

log_info "Uploading template.yaml to s3://${BUCKET}/aws/forwarder/${FORWARDER_VERSION}.yaml"

if [[ ${ACCOUNT} == "prod" ]]; then
    aws_login aws s3 cp template.yaml "s3://${BUCKET}/aws/forwarder/${FORWARDER_VERSION}.yaml" \
        --grants "read=uri=http://acs.amazonaws.com/groups/global/AllUsers"
    aws_login aws s3 cp template.yaml "s3://${BUCKET}/aws/forwarder/latest.yaml" \
        --grants "read=uri=http://acs.amazonaws.com/groups/global/AllUsers"
elif [[ ${ACCOUNT} == "datadog" ]]; then
    aws_login aws s3 cp template.yaml "s3://${BUCKET}/aws/forwarder/${FORWARDER_VERSION}.yaml"
    aws_login aws s3 cp template.yaml "s3://${BUCKET}/aws/forwarder/latest.yaml"
else
    aws_login aws s3 cp template.yaml "s3://${BUCKET}/aws/forwarder-staging/${FORWARDER_VERSION}.yaml"
    aws_login aws s3 cp template.yaml "s3://${BUCKET}/aws/forwarder-staging/latest.yaml"
fi

log_success "Done uploading the CloudFormation template!"

log_info "Here is the CloudFormation quick launch URL:"
log_info "https://console.aws.amazon.com/cloudformation/home#/stacks/new?stackName=datadog-serverless&templateURL=${TEMPLATE_URL}"

log_success ""
log_success "Forwarder release process complete!"

if [[ ${ACCOUNT} == "prod" ]]; then
    log_info "Generating and uploading versions.json for the new release..."

    generate_versions_json
    upload_versions_json

    log_success "Done generating and uploading versions.json!"
    log_info "Please verify the uploaded file:"
    log_info "\thttps://${VERSIONS_BUCKET}.s3.amazonaws.com/forwarder/versions.json"

    log_info "Don't forget to add release notes in GitHub!"
    log_info "\thttps://github.com/DataDog/datadog-serverless-functions/releases"
fi
