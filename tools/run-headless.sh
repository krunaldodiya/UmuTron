#!/usr/bin/env bash
# Run any command, UI test, or check headlessly without opening desktop windows.
set -euo pipefail

export UMUTRON_HEADLESS=1
export GDK_BACKEND="${GDK_BACKEND:-x11}"
export GSK_RENDERER="${GSK_RENDERER:-cairo}"
export GSETTINGS_BACKEND="${GSETTINGS_BACKEND:-memory}"
unset WAYLAND_DISPLAY

if command -v xvfb-run >/dev/null 2>&1; then
    exec xvfb-run -a "$@"
else
    exec "$@"
fi
