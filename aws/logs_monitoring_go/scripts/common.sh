#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

if ((BASH_VERSINFO[0] < 4)); then
    echo "bash 4+ required, found ${BASH_VERSION}" 1>&2
    exit 1
fi

BLUE="" YELLOW="" GREEN="" RED="" RESET=""
if [[ -t 2 ]]; then
    BLUE='\033[0;34m'
    YELLOW='\033[0;33m'
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    RESET='\033[0m'
fi

log_info() {
    printf -- "%b%b%b\n" "${BLUE}" "${*}" "${RESET}" 1>&2
}

log_warning() {
    printf -- "%b%b%b\n" "${YELLOW}" "${*}" "${RESET}" 1>&2
}

log_success() {
    printf -- "%b%b%b\n" "${GREEN}" "${*}" "${RESET}" 1>&2
}

log_error() {
    printf -- "%b%b%b\n" "${RED}" "${*}" "${RESET}" 1>&2
    exit 1
}

user_confirm() {
    local input=""

    if ! : 2>/dev/null </dev/tty; then
        log_error "No terminal available to confirm; this script must be run interactively"
    fi

    read -r -p "${1:-Are you sure}? [y/N] " input </dev/tty

    case "${input}" in
    [yY][eE][sS] | [yY]) return 0 ;;
    *) return 1 ;;
    esac
}

run_traced() {
    log_info "% $(printf '%q ' "${@}")"

    if ! "${@}"; then
        local status=$?
        log_error "FAIL (exit ${status}): $(printf '%q ' "${@}")"
    fi
}

dry_run() {
    if [[ "${DRY_RUN:-true}" == "true" ]]; then
        log_warning "[dry-run] would run: $(printf '%q ' "${@}")"
    else
        run_traced "${@}"
    fi
}
