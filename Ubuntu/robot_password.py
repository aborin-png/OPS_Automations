"""
Robot Password Lookup via internal.bosdyn.com.

Reads your Chrome cookies (from any profile under ~/.config/google-chrome)
and uses them to fetch the Robot Password Lookup page directly with
`requests`. If your Knox session has expired (or the robot-password app
hasn't been authorized yet), the script opens the lookup URL in your
default browser, prompts you to click AUTHORIZE, then polls for the new
cookie and resumes automatically.
"""
import http.cookiejar
import html
import pathlib
import re
import sys
import time
import webbrowser

import browser_cookie3
import requests

from Sheets_Automation.API_fetch import API_Fetch
from Sheets_Automation.Info_Parser import info_parser


LOOKUP_URL = "https://internal.bosdyn.com/robot-password/lookup"
KNOX_HOST = "knox.bostondynamics.com"
AUTH_POLL_INTERVAL = 2.0     # seconds between cookie re-checks
AUTH_TIMEOUT = 180.0         # max seconds to wait for the user to authorize
CHROME_CONFIG = pathlib.Path.home() / ".config" / "google-chrome"


class AuthenticationRequired(RuntimeError):
    pass


def _chrome_cookie_files() -> list[pathlib.Path]:
    """Every per-profile Cookies file under the Chrome config dir."""
    if not CHROME_CONFIG.exists():
        return []
    return [
        d / "Cookies"
        for d in CHROME_CONFIG.iterdir()
        if d.is_dir() and (d / "Cookies").exists()
    ]


def _read_cookies(domain: str = "bosdyn.com") -> http.cookiejar.CookieJar:
    """Combine cookies for `domain` from every Chrome profile we can find."""
    combined = http.cookiejar.CookieJar()
    for cookie_file in _chrome_cookie_files():
        try:
            jar = browser_cookie3.chrome(domain_name=domain, cookie_file=str(cookie_file))
        except Exception:
            continue
        for cookie in jar:
            combined.set_cookie(cookie)
    return combined


def _fetch_lookup_html(serial: str) -> str | None:
    """HTML if authenticated, None if redirected to Knox (no/expired session)."""
    cookies = _read_cookies()
    r = requests.get(
        LOOKUP_URL,
        params={"serial": serial},
        cookies=cookies,
        allow_redirects=True,
        timeout=15,
    )
    if KNOX_HOST in r.url:
        return None
    r.raise_for_status()
    return r.text


def _parse_field(html_text: str, field: str) -> str | None:
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    match = re.search(rf"\b{re.escape(field)}\b\s+(\S+)", text)
    if not match:
        return None
    value = match.group(1)
    return None if value == "None" else value


def _prompt_authorize(serial: str) -> str:
    url = f"{LOOKUP_URL}?serial={serial}"
    profiles = [p.parent.name for p in _chrome_cookie_files()]
    print(f"Authorization required. Opening {url} — click AUTHORIZE in your browser.")
    print(f"Searching Chrome profiles: {profiles or '(none found!)'}")
    webbrowser.open(url)

    deadline = time.monotonic() + AUTH_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(AUTH_POLL_INTERVAL)
        text = _fetch_lookup_html(serial)
        if text is not None:
            print("Authorized. Continuing.")
            return text

    raise AuthenticationRequired(
        f"User did not authorize within {AUTH_TIMEOUT:.0f}s."
    )


def get_robot_password(robot: str, field: str = "web.bd") -> str | None:
    """
    Returns the value of `field` for `serial` from the Robot Password
    Lookup page, or None if the row's value is 'None' or the field
    isn't present.

    On first run (or when the Knox session expires), opens the lookup
    URL in the user's browser, waits for AUTHORIZE, then resumes.
    """
    serial = f'ssd-{info_parser(API_Fetch(robot=robot, robot_offline=[])).description.serial}'

    text = _fetch_lookup_html(serial)
    if text is None:
        text = _prompt_authorize(serial)
    return _parse_field(text, field)


if __name__ == "__main__":
    robot = sys.argv[1] if len(sys.argv) > 1 else "None"
    field = sys.argv[2] if len(sys.argv) > 2 else "web.bd"
    print(get_robot_password(robot, field))