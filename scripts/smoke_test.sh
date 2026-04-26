#!/usr/bin/env bash
# Smoke test a deployed RunLLM backend.
#
# Usage:
#   ./scripts/smoke_test.sh https://your-backend.example.com

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-}}"
if [ -z "$BASE_URL" ]; then
    echo "usage: $0 <base-url>" >&2
    exit 2
fi

fail=0

check() {
    local path="$1"
    local url="${BASE_URL%/}${path}"
    printf 'GET %s ... ' "$url"
    if response=$(curl -fsS -m 15 "$url"); then
        printf 'OK (%s)\n' "$response"
    else
        printf 'FAIL\n'
        fail=1
    fi
}

check /healthz
check /readyz

if [ "$fail" != 0 ]; then
    echo "smoke test failed" >&2
    exit 1
fi
echo "smoke test passed"

