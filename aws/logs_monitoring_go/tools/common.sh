#!/usr/bin/env bash

# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026 Datadog, Inc.

log_info() {
    local BLUE='\033[0;34m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${BLUE}" "${*}" "${RESET}" 1>&2
}

log_warning() {
    local YELLOW='\033[0;33m'
    local RESET='\033[0m'

    printf -- "%b%b%b\n" "${YELLOW}" "${*}" "${RESET}" 1>&2
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
