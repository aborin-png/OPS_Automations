#!/usr/bin/env bash
# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
#
# Reverse of install.sh: remove the application-menu launcher and the file-manager custom icon that
# install.sh created. Does NOT delete the cloned software itself -- just the desktop integration.
#
#     ./uninstall.sh
set -euo pipefail

APP_ID="ops-automations"

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPS_DIR/$APP_ID.desktop"

if [ -e "$DESKTOP_FILE" ]; then
    rm -f "$DESKTOP_FILE"
    echo "removed launcher: $DESKTOP_FILE"
    if command -v update-desktop-database > /dev/null 2>&1; then
        update-desktop-database "$APPS_DIR" > /dev/null 2>&1 || true
    fi
else
    echo "no launcher to remove at $DESKTOP_FILE"
fi

# Clear the custom file-manager icon on whichever executable we can find.
if command -v gio > /dev/null 2>&1; then
    for c in UI_Handler dist/UI_Handler; do
        if [ -e "$HERE/$c" ]; then
            gio set -t unset "$HERE/$c" metadata::custom-icon 2> /dev/null || true
        fi
    done
fi

echo "Uninstalled the OPS Automations desktop integration."
