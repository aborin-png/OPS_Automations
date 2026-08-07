# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Pin/unpin the OPS Automations app to the GNOME dock (Ubuntu taskbar).

Writes a ``~/.local/share/applications/automation-gui.desktop`` launcher and toggles the app in the
GNOME ``favorite-apps`` list via ``gsettings``. GNOME-specific: every function here shells out to
``gsettings``, so callers should be ready for it to fail (e.g. on a non-GNOME desktop). Used by the
Favorites settings window (see dialogs.FavoritesWindow); also runnable as a CLI (``save``/``remove``).
"""
import ast
import os
import subprocess
import sys
import textwrap

DESKTOP_FILE = "automation-gui.desktop"


def pin_to_dock():
    """Add ``automation-gui.desktop`` to the GNOME dock favorites (no-op if already present).

    ``favorite-apps`` is a list literal; it's parsed with ``ast``, appended to, and written back
    (mirrors ``unpin_from_dock``) so an empty or unusual list can't be mangled by string surgery.
    """
    settings = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "favorite-apps"],
                                       universal_newlines=True)
    apps = ast.literal_eval(settings.strip())
    if DESKTOP_FILE not in apps:
        apps.append(DESKTOP_FILE)
        subprocess.check_call(["gsettings", "set", "org.gnome.shell", "favorite-apps", str(apps)])


def is_pinned() -> bool:
    """True if ``automation-gui.desktop`` is currently in the GNOME dock favorites.

    Raises whatever ``gsettings`` raises (e.g. FileNotFoundError on a non-GNOME desktop); callers
    that just want to reflect state should catch that.
    """
    settings = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "favorite-apps"],
                                       universal_newlines=True)
    return DESKTOP_FILE in settings


def unpin_from_dock():
    """Inverse of pin_to_dock: drop automation-gui.desktop from the GNOME dock favorites.

    The favorite-apps value is a list literal (e.g. "['a.desktop', 'automation-gui.desktop']"), so
    it is parsed, filtered, and written back rather than edited as a string, to avoid mangling the
    other entries. No-op if the app isn't currently pinned.
    """
    settings = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "favorite-apps"],
                                       universal_newlines=True)
    if DESKTOP_FILE in settings:
        apps = [app for app in ast.literal_eval(settings.strip()) if app != DESKTOP_FILE]
        subprocess.check_call(["gsettings", "set", "org.gnome.shell", "favorite-apps", str(apps)])


def _desktop_file_path() -> str:
    return os.path.expanduser(f"~/.local/share/applications/{DESKTOP_FILE}")


def save_to_favorites():
    srcdir = os.path.abspath(os.path.dirname(sys.executable)) if getattr(
        sys, 'frozen', False) else os.path.abspath(os.path.dirname(__file__))
    desktop_contents = textwrap.dedent(f"""
        [Desktop Entry]
        Type=Application
        Name=automation-gui
        StartupWMClass=automation-gui
        Exec={srcdir}/UI_Handler
        Icon={srcdir}/assets/icon.png
        Terminal=false
    """).strip()
    with open(_desktop_file_path(), "w") as fout:
        fout.write(desktop_contents)

    pin_to_dock()
    print("added automation-gui to favorites")


def remove_from_favorites():
    filepath = _desktop_file_path()

    if os.path.exists(filepath):
        os.remove(filepath)
        unpin_from_dock()
        print("removed automation-gui from favorites")
    else:
        unpin_from_dock()  # still ensure the dock entry is gone even if the launcher file isn't
        print("file already removed")


if __name__ == "__main__":
    if sys.argv[1] == "save":
        save_to_favorites()
    elif sys.argv[1] == "remove":
        remove_from_favorites()
