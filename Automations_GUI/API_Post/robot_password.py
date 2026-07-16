# Boston Dynamics, Inc. Confidential Information.
# Copyright 2026. All Rights Reserved.
"""Robot Password Lookup via internal.bosdyn.com.

Reads your Chrome/Chromium cookies (from every profile, in both the modern
``<profile>/Network/Cookies`` and legacy ``<profile>/Cookies`` locations) and
uses them to fetch the Robot Password Lookup page directly with `requests`.
This rides your own Knox SSO session against the sanctioned server-side
robot-password service, so the service enforces your DSM permissions and audits
the access as you. If your Knox session has expired (or the robot-password app
hasn't been authorized yet), the script opens the lookup URL in your default
browser, prompts you to click AUTHORIZE, then polls for the new cookie and
resumes automatically.
"""
import html
import http.cookiejar
import logging
import pathlib
import re
import sys
import time
import webbrowser

logger = logging.getLogger("OPS.robot_password")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import browser_cookie3
import requests
from Sheets_Automation.API_fetch import API_Fetch
from Sheets_Automation.Info_Parser import info_parser

LOOKUP_URL = "https://internal.bosdyn.com/robot-password/lookup"
KNOX_HOST = "knox.bostondynamics.com"
AUTH_POLL_INTERVAL = 2.0  # seconds between cookie re-checks
AUTH_TIMEOUT = 180.0  # max seconds to wait for the user to authorize
# Chrome moved its cookie DB to <profile>/Network/Cookies around Chrome 96; older builds (and some
# packagings) still use <profile>/Cookies. Check both, across Chrome and Chromium config dirs, so
# cookie discovery doesn't silently come up empty on a modern browser.
CHROME_CONFIG_DIRS = [
    pathlib.Path.home() / ".config" / "google-chrome",
    pathlib.Path.home() / ".config" / "chromium",
]
COOKIE_SUBPATHS = (("Network", "Cookies"), ("Cookies",))

# In-memory password cache so a robot only has to be authorized once per session.
# Entries live in process memory only (never written to disk, so nothing is hardcoded /
# persisted) and expire after PASSWORD_TTL; the whole cache is gone when the app exits.
PASSWORD_TTL = 60 * 60  # seconds a cached password stays valid
_password_cache: dict[tuple[str, str], tuple[str, float]] = {}


class AuthenticationRequired(RuntimeError):
    pass


def _cache_get(robot: str, field: str) -> str | None:
    """Return a cached, non-expired password for (robot, field), or None."""
    entry = _password_cache.get((robot, field))
    if entry is None:
        return None
    password, expiry = entry
    if time.monotonic() >= expiry:
        _password_cache.pop((robot, field), None)
        return None
    return password


def _cache_set(robot: str, field: str, password: str) -> None:
    _password_cache[(robot, field)] = (password, time.monotonic() + PASSWORD_TTL)


def clear_password_cache() -> None:
    """Drop every cached password (e.g. on GUI shutdown)."""
    _password_cache.clear()


def _chrome_cookie_files() -> list[pathlib.Path]:
    """Every per-profile cookie DB under any Chrome/Chromium config dir (Network/ and legacy)."""
    files: list[pathlib.Path] = []
    for config in CHROME_CONFIG_DIRS:
        if not config.exists():
            continue
        for profile in config.iterdir():
            if not profile.is_dir():
                continue
            for sub in COOKIE_SUBPATHS:
                cookie_file = profile.joinpath(*sub)
                if cookie_file.exists():
                    files.append(cookie_file)
                    break  # prefer the modern Network/Cookies over the legacy path
    return files


def _profile_label(cookie_file: pathlib.Path) -> str:
    """Human-readable '<config>/<profile>' label for a cookie file, for logging."""
    for config in CHROME_CONFIG_DIRS:
        try:
            return f"{config.name}/{cookie_file.relative_to(config).parts[0]}"
        except ValueError:
            continue
    return str(cookie_file)


def _read_cookies(domain: str = "bosdyn.com") -> http.cookiejar.CookieJar:
    """Combine cookies for `domain` from every Chrome/Chromium profile we can find.

    Failures are logged (not silently swallowed) so an empty result is diagnosable: a locked keyring
    / Chrome-open lock reads as read errors, while "signed out" reads as zero cookies.
    """
    combined = http.cookiejar.CookieJar()
    files = _chrome_cookie_files()
    if not files:
        logger.warning("No Chrome/Chromium cookie DB found under %s — is a browser installed?",
                       ", ".join(str(c) for c in CHROME_CONFIG_DIRS))
        return combined

    errors: list[Exception] = []
    total = 0
    for cookie_file in files:
        try:
            jar = browser_cookie3.chrome(domain_name=domain, cookie_file=str(cookie_file))
        except Exception as e:  # noqa: BLE001 -- keep trying other profiles; report at the end
            errors.append(e)
            logger.debug("Could not read cookies from %s: %s", _profile_label(cookie_file), e)
            continue
        count = 0
        for cookie in jar:
            combined.set_cookie(cookie)
            count += 1
        total += count
        logger.debug("Read %d %s cookie(s) from %s", count, domain, _profile_label(cookie_file))

    if total == 0:
        if errors:
            logger.warning(
                "Found %d cookie DB(s) but could not read any (%d error(s)). If Chrome "
                "is open its cookie store may be locked/encrypted — try closing it. "
                "First error: %s", len(files), len(errors), errors[0])
        else:
            logger.warning("No '%s' cookies in any browser profile — you may not be signed in.",
                           domain)
    return combined


def _fetch_lookup_html(serial: str) -> str | None:
    """HTML if authenticated, None if redirected to Knox (no/expired session)."""
    cookies = _read_cookies()
    try:
        r = requests.get(
            LOOKUP_URL,
            params={"serial": serial},
            cookies=cookies,
            allow_redirects=True,
            timeout=15,
        )
    except requests.RequestException as e:
        logger.error("Robot-password lookup request failed for %s: %s", serial, e)
        raise
    if KNOX_HOST in r.url:
        logger.debug("Lookup for %s bounced to Knox — session not authenticated yet.", serial)
        return None
    r.raise_for_status()
    return r.text


def _parse_field(html_text: str, field: str) -> str | None:
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    match = re.search(rf"\b{re.escape(field)}\b\s+(\S+)", text)
    if not match:
        logger.debug("Field %r not present in the lookup page (%d chars parsed).", field, len(text))
        return None
    value = match.group(1)
    return None if value == "None" else value


def _prompt_authorize(serial: str, on_auth_required=None) -> str:
    url = f"{LOOKUP_URL}?serial={serial}"
    profiles = [_profile_label(p) for p in _chrome_cookie_files()]
    logger.info("Authorization required. Opening %s — click AUTHORIZE in your browser.", url)
    logger.debug("Searching Chrome profiles: %s", profiles or "(none found!)")
    if on_auth_required is not None:
        on_auth_required()
    webbrowser.open(url)

    deadline = time.monotonic() + AUTH_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(AUTH_POLL_INTERVAL)
        text = _fetch_lookup_html(serial)
        if text is not None:
            logger.info("Authorized. Continuing.")
            return text

    raise AuthenticationRequired(f"User did not authorize within {AUTH_TIMEOUT:.0f}s.")


def get_robot_password(robot: str, field: str = "web.bd", on_auth_required=None) -> str | None:
    """Returns the value of `field` for `serial` from the Robot Password Lookup page, or None if the
    row's value is 'None' or the field isn't present.

    On first run (or when the Knox session expires), opens the lookup
    URL in the user's browser, waits for AUTHORIZE, then resumes.

    `on_auth_required`, if given, is called (with no arguments) only when
    browser authorization is actually needed, just before the browser opens.
    Callers can use it to surface a "waiting for authorization" UI.

    A successfully retrieved password is cached in memory for PASSWORD_TTL so the
    same robot does not need to be authorized again until it expires or the app exits.
    """
    cached = _cache_get(robot, field)
    if cached is not None:
        return cached

    api = API_Fetch(robot=robot, robot_offline=[])
    if api is None:
        raise Exception("API_Fetch returned None, robot may be offline or unreachable.")

    serial = f'ssd-{info_parser(api).serial}'

    text = _fetch_lookup_html(serial)
    if text is None:
        text = _prompt_authorize(serial, on_auth_required=on_auth_required)
    password = _parse_field(text, field)

    if password is not None:
        _cache_set(robot, field, password)
        logger.info("Retrieved and cached the %r password for %s.", field, robot)
    else:
        logger.info("No %r password available for %s (field absent or 'None').", field, robot)
    return password
