"""
Robot Password Lookup via internal.bosdyn.com.

Attaches to Google Chrome via CDP. If Chrome isn't already listening on
--remote-debugging-port=9222, the script launches it for you. Either way,
the lookup tab is opened inside your normal Chrome (with your work
Google account session intact) and closed at the end.

Caveat: Chrome can only bind a debug port at process startup. If Chrome
is already running without the flag, launching another `google-chrome`
just piggybacks on the existing process and no debug port appears. In
that case the script raises ChromeNotDebuggableError and tells you to
close all Chrome windows and try again.
"""
import re
import shutil
import socket
import subprocess
import sys
import time

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


LOOKUP_URL = "https://internal.bosdyn.com/robot-password/lookup"
CDP_HOST = "localhost"
CDP_PORT = 9222
CDP_URL = f"http://{CDP_HOST}:{CDP_PORT}"


class ChromeNotDebuggableError(RuntimeError):
    pass


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_chrome_binary() -> str | None:
    for name in ("google-chrome-stable", "google-chrome", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _ensure_chrome_debug_port(wait_timeout: float = 15.0) -> None:
    if _is_port_open(CDP_HOST, CDP_PORT):
        return

    binary = _find_chrome_binary()
    if not binary:
        raise ChromeNotDebuggableError(
            "Google Chrome is not installed (no google-chrome binary on PATH)."
        )

    subprocess.Popen(
        [binary, f"--remote-debugging-port={CDP_PORT}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    deadline = time.monotonic() + wait_timeout
    while time.monotonic() < deadline:
        if _is_port_open(CDP_HOST, CDP_PORT):
            return
        time.sleep(0.25)

    raise ChromeNotDebuggableError(
        f"Launched Chrome but no debug port appeared at {CDP_URL} within "
        f"{wait_timeout:.0f}s. Chrome is probably already running without "
        "the debug flag. Close all Chrome windows and try again."
    )


def get_robot_password(serial: str, field: str = "web.bd", timeout_ms: int = 120_000) -> str | None:
    """
    Returns the value of `field` for `serial` from the Robot Password
    Lookup page, or None if the row's value is 'None' or the field
    isn't present. Returns None on timeout (user didn't authorize).

    Raises ChromeNotDebuggableError if Chrome can't be brought up on
    the CDP debug port (usually because Chrome is already running
    without --remote-debugging-port=9222).
    """
    _ensure_chrome_debug_port()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL, timeout=5000)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        try:
            page.goto(f"{LOOKUP_URL}?serial={serial}")
            page.wait_for_url(f"{LOOKUP_URL}*", timeout=timeout_ms)
            page.wait_for_load_state("networkidle")
            text = page.inner_text("body")
        except PlaywrightTimeoutError:
            return None
        finally:
            try:
                page.close()
            except Exception:
                pass

    match = re.search(rf"^{re.escape(field)}\s+(\S+)", text, re.MULTILINE)
    if not match:
        return None
    value = match.group(1)
    return None if value == "None" else value


if __name__ == "__main__":
    serial = sys.argv[1] if len(sys.argv) > 1 else "ssd-122341400713"
    print(get_robot_password(serial))