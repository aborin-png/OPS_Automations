# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Reliable "open this URL in the user's browser" helper.

``webbrowser.open`` is a heuristic: it silently returns False (no exception) when it can't find or
launch a browser, and *what* it finds varies by Python version, session (X11/Wayland) and browser
packaging. In particular a PyInstaller build exports ``LD_LIBRARY_PATH`` / ``LD_PRELOAD`` pointing
at its bundled libraries, which stops snap-packaged browsers (the default on Ubuntu 24.04) from
launching -- so the tab never opens and nothing is logged.

``open_url`` avoids that: on Linux it prefers the freedesktop ``xdg-open`` (which delegates to the
desktop's own default browser) with a cleaned environment, falls back to ``webbrowser``, and logs a
warning on failure instead of failing silently.
"""
import logging
import os
import shutil
import subprocess
import sys
import webbrowser

# Child of the configured "OPS" logger (see logger_setup), so it inherits the app's handlers.
logger = logging.getLogger("OPS.browser")


def _clean_child_env() -> dict:
    """Environment for a launched browser, undoing PyInstaller's dynamic-linker overrides.

    PyInstaller's bootloader points ``LD_LIBRARY_PATH`` (and friends) at its extracted bundle and
    stashes any pre-existing value in ``<VAR>_ORIG``. Passing the bundle paths on to a system or
    snap browser breaks it, so restore the original value (or drop the var entirely if there wasn't
    one). A no-op when not running frozen.
    """
    env = dict(os.environ)
    for var in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_LIBRARY_PATH_64"):
        original = env.pop(f"{var}_ORIG", None)
        if original is not None:
            env[var] = original
        else:
            env.pop(var, None)
    return env


def open_url(url: str) -> bool:
    """Open ``url`` in the user's default browser; return True if a launcher was started.

    On Linux, try ``xdg-open`` first (with a cleaned environment so snap browsers launch), then fall
    back to ``webbrowser``. Everywhere else, use ``webbrowser`` directly.
    """
    if sys.platform.startswith("linux"):
        opener = shutil.which("xdg-open")
        if opener:
            try:
                subprocess.Popen([opener, url], env=_clean_child_env(), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                logger.debug("Opened %s via xdg-open.", url)
                return True
            except Exception as e:  # noqa: BLE001 -- fall back to webbrowser below
                logger.warning("xdg-open failed for %s (%s); falling back to webbrowser.", url, e)

    try:
        if webbrowser.open(url):
            logger.debug("Opened %s via webbrowser.", url)
            return True
    except Exception as e:  # noqa: BLE001 -- reported just below
        logger.warning("webbrowser.open raised for %s: %s", url, e)

    logger.error("Could not open a browser automatically. Open this URL manually: %s", url)
    return False
