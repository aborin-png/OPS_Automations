#!/usr/bin/env bash
# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
#
# One-time installer for the OPS Automations GUI. Run it once, from wherever you cloned the release
# repo:
#
#     ./install.sh
#
# It registers the app -- with its icon -- in your desktop's application menu ("Show Apps" on GNOME),
# using the REAL absolute path of this clone (a .desktop launcher needs absolute Exec=/Icon= paths,
# which aren't known until you clone). It also sets the icon on the UI_Handler file itself in the
# file manager. Re-running it is safe (idempotent). Undo everything with ./uninstall.sh.
#
# No dock pinning is done: find "OPS Automations" in your apps and right-click -> pin if you want it
# on the dock.
set -euo pipefail

APP_ID="ops-automations"   # basename of the installed .desktop file
APP_NAME="OPS Automations" # display name in the menu
WM_CLASS="UI_Handler"      # must match the app window's WM_CLASS so the dock groups it here

# Directory this script lives in (the clone root), resolving symlinks.
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# Locate the executable and icon. Supports both the RELEASE layout (next to this script) and a
# from-source build (dist/ + assets/), so the same script works either way.
find_file() {
    local c
    for c in "$@"; do
        if [ -e "$HERE/$c" ]; then
            echo "$HERE/$c"
            return 0
        fi
    done
    return 1
}

EXE="$(find_file UI_Handler dist/UI_Handler)" || {
    echo "error: UI_Handler executable not found next to install.sh (or in dist/)." >&2
    exit 1
}
ICON="$(find_file icon.png assets/icon.png)" || {
    echo "error: icon.png not found next to install.sh (or in assets/)." >&2
    exit 1
}

chmod +x "$EXE"

APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPS_DIR/$APP_ID.desktop"
mkdir -p "$APPS_DIR"

# Exec is quoted so a clone path containing spaces still launches correctly.
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Boston Dynamics OPS/QA automation GUI
Exec="$EXE"
Icon=$ICON
Path=$HERE
Terminal=false
StartupWMClass=$WM_CLASS
Categories=Utility;
EOF
chmod +x "$DESKTOP_FILE"

# Refresh the menu database so the entry shows up (best-effort; GNOME usually picks it up anyway).
if command -v update-desktop-database > /dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" > /dev/null 2>&1 || true
fi

# Give the executable file itself a custom icon in the file manager (GNOME/Nautilus, per-user).
if command -v gio > /dev/null 2>&1; then
    gio set "$EXE" metadata::custom-icon "file://$ICON" 2> /dev/null || true
fi

echo "Installed '$APP_NAME'."
echo "  launcher : $DESKTOP_FILE"
echo "  exe      : $EXE"
echo "  icon     : $ICON"
echo
echo "Open your apps and search '$APP_NAME' (it may take a few seconds to appear, or a re-login)."
echo "Right-click its icon to pin it to the dock. Undo with ./uninstall.sh."
