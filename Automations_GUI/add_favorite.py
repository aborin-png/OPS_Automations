# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Pin/unpin the OPS Automations app to the GNOME dock (Ubuntu taskbar).

This is the in-app ("Favorites Settings" window -- see dialogs.FavoritesWindow) counterpart to the
one-time ``install.sh`` script, and the two are deliberately kept in sync: they share the *same*
launcher basename (``ops-automations.desktop``), display name, and ``StartupWMClass`` so GNOME sees
a single app -- pinning via right-click (install.sh's launcher) and pinning via this window toggle
the very same dock entry instead of creating a duplicate.

Division of labor:
  * ``install.sh`` / ``uninstall.sh`` own the launcher *file* (register/unregister it in the app
    menu, set the file-manager icon).
  * this module manages only the dock *pin* (the GNOME ``favorite-apps`` list). It will bootstrap a
    launcher if none exists yet (so the button still works when the user never ran install.sh), but
    it never rewrites an existing one (install.sh's has the authoritative absolute paths) and never
    deletes one (that's uninstall.sh's job).

GNOME-specific: every function here shells out to ``gsettings``, so callers should be ready for it
to fail (e.g. on a non-GNOME desktop). Also runnable as a CLI (``save``/``remove``).
"""
import ast
import os
import subprocess
import sys
import textwrap

# Kept identical to install.sh's APP_ID / APP_NAME / WM_CLASS so both mechanisms target one app.
APP_ID = "ops-automations"  # basename (minus .desktop) of the shared launcher
APP_NAME = "OPS Automations"  # display name in the dock / app menu
WM_CLASS = "UI_Handler"  # must match the app window's WM_CLASS so the dock groups it here
DESKTOP_FILE = f"{APP_ID}.desktop"


def _applications_dir() -> str:
    """The XDG applications dir install.sh writes to (honors ``$XDG_DATA_HOME`` like it does)."""
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "applications")


def _desktop_file_path() -> str:
    return os.path.join(_applications_dir(), DESKTOP_FILE)


def pin_to_dock():
    """Add ``ops-automations.desktop`` to the GNOME dock favorites (no-op if already present).

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
    """True if ``ops-automations.desktop`` is currently in the GNOME dock favorites.

    Because the basename matches install.sh's launcher, this also reflects a pin the user made by
    right-clicking the app menu icon. Raises whatever ``gsettings`` raises (e.g. FileNotFoundError
    on a non-GNOME desktop); callers that just want to reflect state should catch that.
    """
    settings = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "favorite-apps"],
                                       universal_newlines=True)
    return DESKTOP_FILE in settings


def unpin_from_dock():
    """Inverse of pin_to_dock: drop ops-automations.desktop from the GNOME dock favorites.

    The favorite-apps value is a list literal (e.g. "['a.desktop', 'ops-automations.desktop']"), so
    it is parsed, filtered, and written back rather than edited as a string, to avoid mangling the
    other entries. No-op if the app isn't currently pinned.
    """
    settings = subprocess.check_output(["gsettings", "get", "org.gnome.shell", "favorite-apps"],
                                       universal_newlines=True)
    if DESKTOP_FILE in settings:
        apps = [app for app in ast.literal_eval(settings.strip()) if app != DESKTOP_FILE]
        subprocess.check_call(["gsettings", "set", "org.gnome.shell", "favorite-apps", str(apps)])


def _app_dir() -> str:
    """Absolute directory the app runs from (the release/clone dir), i.e. install.sh's ``$HERE``."""
    anchor = sys.executable if getattr(sys, "frozen", False) else __file__
    return os.path.abspath(os.path.dirname(anchor))


def _find_first(base: str, *candidates: str) -> str:
    """First existing ``base/candidate`` path; falls back to ``base/<last candidate>`` if none exist
    (mirrors install.sh's ``find_file`` across the release + from-source layouts)."""
    for rel in candidates:
        path = os.path.join(base, rel)
        if os.path.exists(path):
            return path
    return os.path.join(base, candidates[-1])


def _launcher_contents() -> str:
    """A .desktop launcher equivalent to the one install.sh writes (same Name / WM class / fields).

    When frozen, ``Exec`` is the running executable itself (authoritative); from source we probe the
    same spots install.sh does (``UI_Handler`` then ``dist/UI_Handler``). The icon probes ``icon.png``
    then ``assets/icon.png`` -- an on-disk path, since the .desktop entry can't point into the exe's
    temporary extraction dir.
    """
    app_dir = _app_dir()
    if getattr(sys, "frozen", False):
        exe = sys.executable
    else:
        exe = _find_first(app_dir, "UI_Handler", "dist/UI_Handler")
    icon = _find_first(app_dir, "icon.png", "assets/icon.png")
    return textwrap.dedent(f"""
        [Desktop Entry]
        Type=Application
        Name={APP_NAME}
        Comment=Boston Dynamics OPS/QA automation GUI
        Exec="{exe}"
        Icon={icon}
        Path={app_dir}
        Terminal=false
        StartupWMClass={WM_CLASS}
        Categories=Utility;
    """).strip()


def save_to_favorites():
    """Pin the app to the GNOME dock, sharing install.sh's launcher so there's never a duplicate.

    If the shared launcher already exists (e.g. install.sh created it), it's left untouched -- it
    has the authoritative absolute paths -- and we only add the dock pin. Otherwise we bootstrap an
    equivalent launcher first, so the button still works for users who never ran install.sh.
    """
    path = _desktop_file_path()
    if not os.path.exists(path):
        os.makedirs(_applications_dir(), exist_ok=True)
        with open(path, "w") as fout:
            fout.write(_launcher_contents())
        print(f"created launcher: {path}")
    pin_to_dock()
    print(f"added '{APP_NAME}' to favorites")


def remove_from_favorites():
    """Unpin the app from the GNOME dock.

    Only the dock pin is removed -- the launcher file is left in place, because it's shared with
    install.sh's app-menu registration (removing it entirely is uninstall.sh's job). This mirrors
    "remove from favorites" meaning *unpin*, not *uninstall*.
    """
    unpin_from_dock()
    print(f"removed '{APP_NAME}' from favorites")


if __name__ == "__main__":
    if sys.argv[1] == "save":
        save_to_favorites()
    elif sys.argv[1] == "remove":
        remove_from_favorites()
