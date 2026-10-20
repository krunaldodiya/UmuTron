#!/usr/bin/env bash
# Launch the native desktop app against the local UmuTron-FastAPI Docker stack.
#
# The internal API key is read from the environment first, then from the
# FastAPI project's .env file. Override the API location with UMUTRON_API_DIR.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_DIR="${UMUTRON_API_DIR:-$ROOT/../UmuTron-FastAPI}"
API_URL="${APP_BASE_URL:-http://127.0.0.1:8000}"

if [[ -z "${INTERNAL_API_KEY:-}" && -f "$API_DIR/.env" ]]; then
    INTERNAL_API_KEY="$(
        awk -F= '
            $1 == "INTERNAL_API_KEY" {
                sub(/^[^=]*=/, "")
                sub(/\r$/, "")
                print
                exit
            }
        ' "$API_DIR/.env"
    )"
fi

if [[ -z "${INTERNAL_API_KEY:-}" ]]; then
    cat >&2 <<'EOF'
INTERNAL_API_KEY is not set.

Start the local API first:
  cd UmuTron-FastAPI && docker compose up -d

Then either export the key used by that stack:
  export INTERNAL_API_KEY="$(awk -F= '$1=="INTERNAL_API_KEY"{print $2}' UmuTron-FastAPI/.env)"
or run this helper from the workspace where UmuTron-FastAPI/.env exists.
EOF
    exit 1
fi

export APP_BASE_URL="$API_URL"
export UMUTRON_ALLOW_LOOPBACK_HTTP=1
export UMUTRON_API_DIR="$API_DIR"
export INTERNAL_API_KEY
# Compatibility adapters read this name; the main desktop paths use the
# public source/catalog routes and do not transmit the key to remote hosts.
export UMUTRON_API_KEY="$INTERNAL_API_KEY"

if command -v curl >/dev/null 2>&1; then
    if ! curl -fsS --max-time 2 "$API_URL/health" >/dev/null 2>&1; then
        printf 'warning: %s is not responding; starting the desktop anyway.\n' "$API_URL" >&2
    fi
fi

exec "${PYTHON:-python3}" "$ROOT/run.py" "$@"
