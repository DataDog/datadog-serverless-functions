#!/usr/bin/env bash
#
# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-Present Datadog, Inc.
#
# Regenerates the LICENSES/ directory: one entry per third-party Go module that is
# linked into the forwarder binary, holding that module's full license text.
#
# Usage:
#   scripts/update_licenses.sh           regenerate LICENSES/
#   scripts/update_licenses.sh --verify  fail if LICENSES/ is stale (for CI)

set -o errexit
set -o nounset
set -o pipefail

MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly MODULE_DIR
readonly LICENSES_DIR="${MODULE_DIR}/LICENSES"

# Entrypoint whose linked dependencies define what actually ships.
readonly ENTRYPOINT="./cmd/forwarder/"
readonly GO_LICENSES_VERSION="v2.0.1"
readonly OWN_MODULE="github.com/DataDog/datadog-serverless-functions"

cd "${MODULE_DIR}"

generate_into() {
  local out_dir="$1"

  go run "github.com/google/go-licenses/v2@${GO_LICENSES_VERSION}" save "${ENTRYPOINT}" \
    --save_path="${out_dir}" \
    --ignore "${OWN_MODULE}" \
    --force
}

if [[ "${1:-}" == "--verify" ]]; then
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' EXIT
  generate_into "${tmp_dir}/LICENSES"
  if ! diff -r -q "${LICENSES_DIR}" "${tmp_dir}/LICENSES" >/dev/null 2>&1; then
    echo "LICENSES/ is out of date. Run: make licenses" >&2
    diff -r "${LICENSES_DIR}" "${tmp_dir}/LICENSES" >&2 || true
    exit 1
  fi
  echo "LICENSES/ is up to date."
  exit 0
fi

generate_into "${LICENSES_DIR}"
echo "Wrote ${LICENSES_DIR}."
